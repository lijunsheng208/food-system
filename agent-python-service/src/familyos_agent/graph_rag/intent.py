"""使用真实 LLM 将自然语言问题转换为统一 RetrievalPlan。"""

import json
from typing import Any

from .models import GraphQueryPlan, GraphQueryType, RetrievalPlan


class LLMIntentClassifier:
    """通过 OpenAI-compatible 模型完成检索意图识别和图查询规划。"""

    def __init__(self, model: Any) -> None:
        if model is None or not hasattr(model, "invoke"):
            raise ValueError("意图分类模型必须实现 invoke")
        self._model = model

    # classify 将模型 JSON 严格转换为受控计划；解析失败时只回退向量检索。
    def classify(self, query: str) -> RetrievalPlan:
        text = query.strip()
        if not text:
            raise ValueError("检索问题不能为空")
        messages = [
            {"role": "system", "content": (
                "你是 FamilyOS 检索意图分类器，只输出 JSON，不生成 Cypher。"
                "route 只能是 vector、graph、hybrid。普通语义问题用 vector；"
                "需要实体关系、多跳步骤或子图推理用 graph；同时需要图关系和完整原文用 hybrid。"
                "vector_query 必须是适合向量检索的完整查询。graph.source_entities 只能填写问题中明确出现的实体名称。"
                "格式：{\"route\":\"vector\",\"vector_query\":\"...\",\"graph\":{"
                "\"query_type\":\"entity_relation\",\"source_entities\":[],\"target_entities\":[],"
                "\"relation_types\":[],\"max_depth\":2,\"max_nodes\":20}}"
            )},
            {"role": "user", "content": text},
        ]
        try:
            response = self._model.invoke(messages)
            raw = response.get("content", "") if isinstance(response, dict) else getattr(response, "content", "")
            payload = self._parse_json(str(raw))
            return self._from_payload(text, payload)
        except Exception:
            # 分类服务异常不能阻塞基础检索，也不能伪造一个无法命中的图计划。
            return RetrievalPlan("vector", text)

    # _parse_json 兼容模型偶尔返回的 Markdown JSON 代码块。
    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        content = raw.strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("意图分类结果必须是 JSON 对象")
        return value

    # _from_payload 校验路由字段并构造不可执行 Cypher 的 GraphQueryPlan。
    @staticmethod
    def _from_payload(query: str, payload: dict[str, Any]) -> RetrievalPlan:
        route = str(payload.get("route", "vector")).strip().lower()
        if route not in {"vector", "graph", "hybrid"}:
            route = "vector"
        vector_query = str(payload.get("vector_query", query)).strip() or query
        graph = payload.get("graph")
        if route in {"graph", "hybrid"} and isinstance(graph, dict):
            entities = [str(item).strip() for item in graph.get("source_entities", []) if str(item).strip()][:10]
            if entities:
                query_type = GraphQueryType(str(graph.get("query_type", "entity_relation")))
                relations = [str(item).strip() for item in graph.get("relation_types", []) if str(item).strip()]
                plan = GraphQueryPlan(
                    query_type=query_type,
                    source_entities=entities,
                    target_entities=[str(item).strip() for item in graph.get("target_entities", []) if str(item).strip()][:10],
                    relation_types=relations,
                    max_depth=int(graph.get("max_depth", 2)),
                    max_nodes=int(graph.get("max_nodes", 20)),
                )
                return RetrievalPlan(route, vector_query, plan)
        # 模型没有给出明确实体时，图查询没有可靠起点，安全降级为向量。
        return RetrievalPlan("vector", vector_query)
