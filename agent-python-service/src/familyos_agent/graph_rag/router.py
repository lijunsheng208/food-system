"""阶段 4 受控路由与统一计划驱动的组合检索编排。"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Callable

from ..retrieval import RetrievalQuery
from .models import GraphQueryPlan, GraphQueryType, RetrievalPlan


class ControlledRetriever:
    """根据 RetrievalPlan 选择向量、图或组合检索，并统一去重结果。"""

    def __init__(self, vector_retriever: Any, graph_retriever: Any | None = None, tool_resolver: Callable[..., Any] | None = None, planner: Callable[[str], GraphQueryPlan] | None = None, timeout: float = 5.0, intent_classifier: Callable[[str], RetrievalPlan] | None = None) -> None:
        if vector_retriever is None or timeout <= 0:
            raise ValueError("组合检索配置无效")
        self._vector = vector_retriever
        self._graph = graph_retriever
        self._tool = tool_resolver
        self._planner = planner or self._default_plan
        self._intent_classifier = intent_classifier
        self._timeout = timeout

    # classify 保留无 LLM 分类器时的规则兼容路径。
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

    # retrieve 执行统一 RetrievalPlan，并按 canonical chunk_id 去重图和向量证据。
    def retrieve(self, query: str, user_id: int, knowledge_base_id: int, index_version: int = 0, top_k: int = 5, strategy: str | None = None, plan: RetrievalPlan | None = None) -> dict[str, Any]:
        text = query.strip()
        if not text:
            raise ValueError("检索问题不能为空")
        if plan is None:
            if strategy is not None:
                route = strategy
                plan = RetrievalPlan(route, text, self._planner(text) if route in {"graph", "hybrid"} else None)
            elif self._intent_classifier is not None:
                plan = self._intent_classifier(text)
            else:
                route = self.classify(text)
                plan = RetrievalPlan(route, text, self._planner(text) if route in {"graph", "hybrid"} else None)
        base: dict[str, Any] = {"route_strategy": plan.route, "graph_results": [], "tool_constraints": {}, "documents": [], "fallback_reason": "", "retrieval_plan": plan}
        if plan.route == "no_retrieval":
            return base
        if plan.route == "tool" and self._tool is not None:
            try:
                base["tool_constraints"] = self._call(self._tool, text, user_id, knowledge_base_id) or {}
            except Exception:
                base["fallback_reason"] = "TOOL_UNAVAILABLE"
        if plan.route in {"graph", "hybrid"}:
            graph_ok = False
            if self._graph is not None and plan.graph_plan is not None:
                try:
                    graph_result = self._call(self._graph.retrieve, plan.graph_plan, user_id, knowledge_base_id, index_version)
                    base["graph_results"] = graph_result.get("results", [])
                    self._append_unique(base["documents"], graph_result.get("evidence", []))
                    graph_ok = bool(base["documents"])
                except Exception as exc:
                    base["fallback_reason"] = "GRAPH_TIMEOUT" if isinstance(exc, TimeoutError) else "GRAPH_UNAVAILABLE"
            if plan.route == "graph" and not graph_ok:
                self._retrieve_vector(base, text, user_id, knowledge_base_id, index_version, top_k)
            elif plan.route == "hybrid":
                self._retrieve_vector(base, plan.vector_query, user_id, knowledge_base_id, index_version, top_k)
            return base
        # 纯 Vector 必须保持旧评估口径，直接检索原始问题；改写文本只供 Hybrid 使用。
        self._retrieve_vector(base, text, user_id, knowledge_base_id, index_version, top_k)
        return base

    # _retrieve_vector 执行 Milvus 检索并把不同返回类型统一为 canonical chunk_id 去重。
    def _retrieve_vector(self, base: dict[str, Any], query: str, user_id: int, knowledge_base_id: int, index_version: int, top_k: int) -> None:
        try:
            rows = self._call(self._vector.retrieve, RetrievalQuery(query, knowledge_base_id, user_id, top_k, index_version=index_version))
            self._append_unique(base["documents"], rows)
        except Exception as exc:
            if not base["documents"]:
                base["fallback_reason"] = "VECTOR_TIMEOUT" if isinstance(exc, TimeoutError) else "VECTOR_UNAVAILABLE"

    # _append_unique 兼容 Evidence、RetrievedChunk 和字典结果的 canonical 标识取值。
    @classmethod
    def _append_unique(cls, target: list[Any], values: Any) -> None:
        if not values:
            return
        seen = {cls._chunk_id(item) for item in target if cls._chunk_id(item)}
        for item in values:
            chunk_id = cls._chunk_id(item)
            if not chunk_id or chunk_id not in seen:
                target.append(item)
                if chunk_id:
                    seen.add(chunk_id)

    # _chunk_id 统一读取对象属性或 mapping 中的 chunk_id/source_chunk_id。
    @staticmethod
    def _chunk_id(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("chunk_id", item.get("source_chunk_id", "")) or "")
        return str(getattr(item, "chunk_id", getattr(item, "source_chunk_id", "")) or "")

    # _call 通过线程超时隔离 Neo4j、Milvus 和外部 Tool 的阻塞调用。
    def _call(self, function: Callable[..., Any], *args: Any) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(function, *args)
        try:
            return future.result(timeout=self._timeout)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    # _default_plan 为未配置 LLM 时提供保守规则计划，仅使用完整查询作为兼容实体。
    @staticmethod
    def _default_plan(query: str) -> GraphQueryPlan:
        query_type = GraphQueryType.MULTI_HOP if any(word in query for word in ("几步", "先后", "之后")) else GraphQueryType.ENTITY_RELATION
        return GraphQueryPlan(query_type, [query[:200]], max_depth=2, max_nodes=20)
