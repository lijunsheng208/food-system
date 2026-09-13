"""阶段 3 只读图检索编排，隔离 Neo4j 结果和证据回查。"""

from typing import Any, Callable, Mapping, Sequence

from .models import Evidence, GraphQueryPlan


class GraphRetriever:
    """执行受权限约束的实体、路径和子图检索。"""

    # 初始化图存储和可选的原文块回查适配器。
    def __init__(self, repository: Any, chunk_resolver: Callable[..., Sequence[Mapping[str, Any]]] | None = None) -> None:
        if repository is None:
            raise ValueError("图 Repository 不能为空")
        self._repository = repository
        self._chunk_resolver = chunk_resolver

    # 检索源实体的一跳关系，适用于“某菜需要哪些食材”类问题。
    def search_entity_relations(self, entity_names: Sequence[str], user_id: int, knowledge_base_id: int, index_version: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        return self._repository.search_entity_relations(entity_names, user_id, knowledge_base_id, index_version, limit)

    # 检索受控深度的多跳路径，深度和数量由查询计划进一步限制。
    def search_paths(self, plan: GraphQueryPlan, user_id: int, knowledge_base_id: int, index_version: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        return self._repository.search_paths(plan.source_entities, user_id, knowledge_base_id, index_version, plan.max_depth, min(limit, plan.max_nodes))

    # 检索源实体周围的受控子图，避免将整个知识库暴露给生成模型。
    def search_subgraph(self, plan: GraphQueryPlan, user_id: int, knowledge_base_id: int, index_version: int = 0) -> list[dict[str, Any]]:
        return self._repository.search_subgraph(plan.source_entities, user_id, knowledge_base_id, index_version, plan.max_depth, plan.max_nodes)

    # 将图节点携带的 source_chunk_id 回查为统一 Evidence，保留权限和版本条件。
    def resolve_evidence(self, source_chunk_ids: Sequence[str], user_id: int, knowledge_base_id: int, index_version: int = 0) -> list[Evidence]:
        if not source_chunk_ids:
            return []
        metadata = self._repository.resolve_evidence(source_chunk_ids, user_id, knowledge_base_id, index_version)
        content_by_chunk: dict[str, Mapping[str, Any]] = {}
        if self._chunk_resolver:
            content_by_chunk = {str(row.get("chunk_id", row.get("source_chunk_id", ""))): row for row in self._chunk_resolver(source_chunk_ids, user_id, knowledge_base_id, index_version)}
        evidence: list[Evidence] = []
        for row in metadata:
            chunk_id = str(row.get("source_chunk_id", ""))
            chunk = content_by_chunk.get(chunk_id, row)
            content = str(chunk.get("content", "")).strip()
            if not content:
                continue
            evidence.append(Evidence("document", content, user_id, knowledge_base_id, int(row.get("document_id", 0) or 0), chunk_id, str(row.get("source_page", "")) or None, index_version=int(row.get("index_version", index_version) or index_version), confidence=float(row.get("confidence", 1.0))))
        return evidence

    # 根据受控查询计划执行图检索，并可选地回查原文证据。
    def retrieve(self, plan: GraphQueryPlan, user_id: int, knowledge_base_id: int, index_version: int = 0, resolve_evidence: bool = True) -> dict[str, Any]:
        if plan.query_type.value == "entity_relation":
            rows = self.search_entity_relations(plan.source_entities, user_id, knowledge_base_id, index_version, plan.max_nodes)
        elif plan.query_type.value == "multi_hop":
            rows = self.search_paths(plan, user_id, knowledge_base_id, index_version, plan.max_nodes)
        else:
            rows = self.search_subgraph(plan, user_id, knowledge_base_id, index_version)
        ids = self._source_chunk_ids(rows)
        return {"results": rows, "evidence": self.resolve_evidence(ids, user_id, knowledge_base_id, index_version) if resolve_evidence else []}

    # 从 Neo4j 返回的节点、关系或路径记录中提取原文块标识。
    @staticmethod
    def _source_chunk_ids(rows: Sequence[Mapping[str, Any]]) -> list[str]:
        found: list[str] = []
        def visit(value: Any) -> None:
            if isinstance(value, Mapping):
                chunk_id = value.get("source_chunk_id")
                if chunk_id and str(chunk_id) not in found:
                    found.append(str(chunk_id))
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, (list, tuple)):
                for nested in value:
                    visit(nested)
            elif hasattr(value, "items"):
                visit(dict(value.items()))
            elif hasattr(value, "nodes"):
                visit(list(value.nodes))
        for row in rows:
            visit(row)
        return found
