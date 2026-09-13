"""Neo4j 图数据持久化及只读检索边界。"""

from typing import Any, Iterable, Mapping, Sequence

from .models import GraphEntity, GraphRelation


class Neo4jGraphRepository:
    """使用参数化 Cypher 写入图实体和关系。"""

    def __init__(self, driver: object) -> None:
        if driver is None:
            raise ValueError("Neo4j driver 不能为空")
        self._driver = driver

    # 替换单个文档版本，先删除旧版本图数据再写入当前候选。
    def replace_version(self, document_id: int, index_version: int, entities: Iterable[GraphEntity], relations: Iterable[GraphRelation]) -> None:
        entities, relations = list(entities), list(relations)
        with self._driver.session() as session:
            session.run("MATCH (n {document_id: $document_id, index_version: $index_version}) DETACH DELETE n", document_id=document_id, index_version=index_version)
            for entity in entities:
                session.run("MERGE (n {entity_id: $entity_id}) SET n += $props", entity_id=entity.entity_id, props=entity.__dict__)
            for relation in relations:
                if relation.relation_type not in {"REQUIRES", "CONTAINS_STEP", "BELONGS_TO_CATEGORY", "SUITABLE_FOR", "PAIRS_WITH", "PRECEDES"}:
                    raise ValueError("不支持的图关系类型: %s" % relation.relation_type)
                # 关系类型来自代码白名单，使用静态 Cypher 标识符避免依赖 APOC 和动态拼接用户输入。
                query = "MATCH (a {entity_id: $source}), (b {entity_id: $target}) MERGE (a)-[r:%s]->(b) SET r += $props" % relation.relation_type
                session.run(query, source=relation.source_entity_id, target=relation.target_entity_id, props=relation.__dict__)

    # 删除单个文档版本，供索引失败补偿使用。
    def delete_version(self, document_id: int, index_version: int) -> None:
        with self._driver.session() as session:
            session.run("MATCH (n {document_id: $document_id, index_version: $index_version}) DETACH DELETE n", document_id=document_id, index_version=index_version)

    # 查询与实体直接相连的关系，所有租户和版本条件均通过参数绑定。
    def search_entity_relations(self, entity_names: Sequence[str], user_id: int, knowledge_base_id: int, index_version: int = 0, limit: int = 20) -> list[dict[str, Any]]:
        self._validate_scope(entity_names, user_id, knowledge_base_id, index_version, limit)
        query = """MATCH (a)-[r]->(b)
WHERE a.name IN $entity_names AND a.user_id = $user_id AND b.user_id = $user_id
  AND a.knowledge_base_id = $knowledge_base_id AND b.knowledge_base_id = $knowledge_base_id
  AND r.user_id = $user_id AND r.knowledge_base_id = $knowledge_base_id
  AND a.status = 'active' AND b.status = 'active' AND r.status = 'active'
  AND ($index_version = 0 OR (a.index_version = $index_version AND b.index_version = $index_version AND r.index_version = $index_version))
RETURN a, r, b LIMIT $limit"""
        return self._read(query, entity_names=list(entity_names), user_id=user_id, knowledge_base_id=knowledge_base_id, index_version=index_version, limit=limit)

    # 查询受控深度内的路径，不允许用户输入拼接进 Cypher。
    def search_paths(self, source_entities: Sequence[str], user_id: int, knowledge_base_id: int, index_version: int = 0, max_depth: int = 2, limit: int = 20) -> list[dict[str, Any]]:
        self._validate_scope(source_entities, user_id, knowledge_base_id, index_version, limit)
        if max_depth <= 0 or max_depth > 3:
            raise ValueError("图遍历深度必须在 1 到 3 之间")
        query = """MATCH p=(start)-[*1..3]->(end)
WHERE start.name IN $source_entities AND start.user_id = $user_id AND end.user_id = $user_id
  AND start.knowledge_base_id = $knowledge_base_id AND end.knowledge_base_id = $knowledge_base_id
  AND all(n IN nodes(p) WHERE n.status = 'active' AND n.user_id = $user_id AND n.knowledge_base_id = $knowledge_base_id
    AND ($index_version = 0 OR n.index_version = $index_version))
  AND all(r IN relationships(p) WHERE r.status = 'active' AND r.user_id = $user_id
    AND r.knowledge_base_id = $knowledge_base_id
    AND ($index_version = 0 OR r.index_version = $index_version))
  AND length(p) <= $max_depth
RETURN p LIMIT $limit"""
        return self._read(query, source_entities=list(source_entities), user_id=user_id, knowledge_base_id=knowledge_base_id, index_version=index_version, max_depth=max_depth, limit=limit)

    # 查询实体邻域子图，返回节点和关系的原始记录供 GraphRetriever 组装。
    def search_subgraph(self, source_entities: Sequence[str], user_id: int, knowledge_base_id: int, index_version: int = 0, max_depth: int = 2, max_nodes: int = 50) -> list[dict[str, Any]]:
        self._validate_scope(source_entities, user_id, knowledge_base_id, index_version, max_nodes)
        if max_depth <= 0 or max_depth > 3 or max_nodes <= 0 or max_nodes > 200:
            raise ValueError("子图查询边界无效")
        query = """MATCH p=(start)-[*0..3]-(n)
WHERE start.name IN $source_entities AND start.user_id = $user_id AND n.user_id = $user_id
  AND start.knowledge_base_id = $knowledge_base_id AND n.knowledge_base_id = $knowledge_base_id
  AND all(x IN nodes(p) WHERE x.status = 'active' AND ($index_version = 0 OR x.index_version = $index_version))
  AND length(p) <= $max_depth
RETURN p LIMIT $max_nodes"""
        return self._read(query, source_entities=list(source_entities), user_id=user_id, knowledge_base_id=knowledge_base_id, index_version=index_version, max_depth=max_depth, max_nodes=max_nodes)

    # 按来源块查询原文证据，实际文本回查由上层 Repository 适配。
    def resolve_evidence(self, source_chunk_ids: Sequence[str], user_id: int, knowledge_base_id: int, index_version: int = 0) -> list[dict[str, Any]]:
        self._validate_scope(source_chunk_ids, user_id, knowledge_base_id, index_version, 200)
        query = """MATCH (n)
WHERE n.source_chunk_id IN $source_chunk_ids AND n.user_id = $user_id
  AND n.knowledge_base_id = $knowledge_base_id AND n.status = 'active'
  AND ($index_version = 0 OR n.index_version = $index_version)
RETURN DISTINCT n.source_chunk_id AS source_chunk_id, n.document_id AS document_id,
  n.index_version AS index_version, n.source_page AS source_page"""
        return self._read(query, source_chunk_ids=list(source_chunk_ids), user_id=user_id, knowledge_base_id=knowledge_base_id, index_version=index_version)

    # 统一执行只读查询，兼容 Neo4j Record 和测试字典结果。
    def _read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            result = session.run(query, **params)
            rows = []
            for record in result:
                rows.append(dict(record) if isinstance(record, Mapping) else dict(record.items()))
            return rows

    # 校验跨租户查询边界，避免空实体或非法分页进入数据库。
    @staticmethod
    def _validate_scope(values: Sequence[str], user_id: int, knowledge_base_id: int, index_version: int, limit: int) -> None:
        if not values or any(not str(value).strip() for value in values):
            raise ValueError("图查询实体不能为空")
        if user_id <= 0 or knowledge_base_id <= 0 or index_version < 0 or limit <= 0:
            raise ValueError("图查询权限或数量参数无效")
