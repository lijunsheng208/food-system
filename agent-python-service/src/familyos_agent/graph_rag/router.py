"""阶段 4 受控路由与组合检索编排。"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Callable, Mapping, Sequence

from ..retrieval import RetrievalQuery
from .models import GraphQueryPlan, GraphQueryType


class ControlledRetriever:
    """根据查询意图选择向量、图或组合检索，并在异常时安全回退。"""

    def __init__(self, vector_retriever: Any, graph_retriever: Any | None = None, tool_resolver: Callable[..., Any] | None = None, planner: Callable[[str], GraphQueryPlan] | None = None, timeout: float = 5.0) -> None:
        if vector_retriever is None or timeout <= 0:
            raise ValueError("组合检索配置无效")
        self._vector = vector_retriever
        self._graph = graph_retriever
        self._tool = tool_resolver
        self._planner = planner or self._default_plan
        self._timeout = timeout

    # classify 判断是否包含关系、多跳或实时约束意图，普通问题保持向量路径。
    @staticmethod
    def classify(query: str) -> str:
        text = query.strip()
        if not text:
            raise ValueError("检索问题不能为空")
        if any(word in text for word in ("实时", "今天", "现在", "库存", "价格", "天气")):
            return "tool"
        if any(word in text for word in ("为什么", "关系", "需要", "搭配", "属于", "几步", "先后", "之后")):
            return "graph"
        return "vector"

    # retrieve 执行路由，图失败、超时或空结果时回退到向量检索。
    def retrieve(self, query: str, user_id: int, knowledge_base_id: int, index_version: int = 0, top_k: int = 5, strategy: str | None = None) -> dict[str, Any]:
        strategy = strategy or self.classify(query)
        if strategy not in {"vector", "graph", "tool", "hybrid", "no_retrieval"}:
            raise ValueError("不支持的检索意图: %s" % strategy)
        base = {"route_strategy": strategy, "graph_results": [], "tool_constraints": {}, "documents": [], "fallback_reason": ""}
        if strategy == "no_retrieval":
            return base
        if strategy == "hybrid":
            strategy = "graph"
        if strategy == "tool" and self._tool is not None:
            try:
                base["tool_constraints"] = self._call(self._tool, query, user_id, knowledge_base_id) or {}
            except Exception:
                base["fallback_reason"] = "TOOL_UNAVAILABLE"
        if strategy in {"graph", "tool"} and self._graph is not None:
            try:
                plan = self._planner(query)
                graph_result = self._call(self._graph.retrieve, plan, user_id, knowledge_base_id, index_version)
                base["graph_results"] = graph_result.get("results", [])
                evidence = graph_result.get("evidence", [])
                base["documents"].extend(evidence)
                if base["documents"]:
                    base["route_strategy"] = "graph+vector"
            except Exception as exc:
                base["fallback_reason"] = "GRAPH_TIMEOUT" if isinstance(exc, TimeoutError) else "GRAPH_UNAVAILABLE"
        # 组合策略始终执行一次向量检索，以获得可引用的原文块；普通问题只执行向量检索。
        try:
            rows = self._call(self._vector.retrieve, RetrievalQuery(query, knowledge_base_id, user_id, top_k, index_version=index_version))
            seen = {getattr(item, "chunk_id", None) for item in base["documents"]}
            for row in rows:
                if getattr(row, "chunk_id", None) not in seen:
                    base["documents"].append(row)
        except Exception as exc:
            if not base["documents"]:
                base["fallback_reason"] = "VECTOR_TIMEOUT" if isinstance(exc, TimeoutError) else "VECTOR_UNAVAILABLE"
        return base

    # 通过线程超时隔离 Neo4j、Milvus 和外部实时 Tool 的阻塞调用。
    def _call(self, function: Callable[..., Any], *args: Any) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(function, *args)
        try:
            return future.result(timeout=self._timeout)
        finally:
            # 超时后不等待外部服务自行结束，避免阻塞 Agent 主流程；底层调用仍由其客户端负责清理。
            executor.shutdown(wait=False, cancel_futures=True)

    # 为没有 LLM 查询规划器的阶段 4 实验提供保守的规则计划。
    @staticmethod
    def _default_plan(query: str) -> GraphQueryPlan:
        query_type = GraphQueryType.MULTI_HOP if any(word in query for word in ("几步", "先后", "之后")) else GraphQueryType.ENTITY_RELATION
        return GraphQueryPlan(query_type, [query[:200]], max_depth=2, max_nodes=20)
