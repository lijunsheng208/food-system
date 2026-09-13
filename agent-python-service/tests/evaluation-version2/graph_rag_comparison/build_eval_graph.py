"""用正式评估 chunk ID 重建隔离的 Neo4j Graph RAG 评估空间。"""

import json
from pathlib import Path

from neo4j import GraphDatabase

from familyos_agent.graph_rag import Neo4jGraphRepository
from familyos_agent.graph_rag.models import GraphEntity, GraphRelation


ROOT = Path(__file__).resolve().parents[3]
GRAPH = ROOT / "evaluation/experiments/graph-stage1/candidates.jsonl"
CHUNKS = ROOT / "evaluation/datasets/raw/chunks.jsonl"
MAPPING = Path(__file__).resolve().parent / "graph_to_milvus_chunk_mapping.jsonl"
USER_ID = 900001
KNOWLEDGE_BASE_ID = 900001
INDEX_VERSION = 1


def _source_name(value: str) -> str:
    """统一候选图绝对路径和评估 chunk 的相对 source。"""
    marker = "/dishes/"
    return value.split(marker, 1)[1] if marker in value else Path(value).name


def main() -> None:
    """清理评估命名空间并写入带 canonical document/chunk ID 的图数据。"""
    graph_rows = [json.loads(line) for line in GRAPH.read_text(encoding="utf-8").splitlines() if line.strip()]
    chunk_rows = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line.strip()]
    mappings = [json.loads(line) for line in MAPPING.read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks_by_source = {row["source"]: row for row in chunk_rows if row["chunk_index"] == 0}
    entity_mapping = {row["graph_entity_id"]: row for row in mappings}
    source_mapping = {}
    for row in mappings:
        if row.get("milvus_chunk_id"):
            source_mapping.setdefault((row["source"], row["graph_source_chunk_id"]), row)

    driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "familyos_dev"))
    driver.verify_connectivity()
    repository = Neo4jGraphRepository(driver)
    with driver.session() as session:
        session.run(
            "MATCH (n {user_id: $user_id, knowledge_base_id: $knowledge_base_id, index_version: $index_version}) DETACH DELETE n",
            user_id=USER_ID,
            knowledge_base_id=KNOWLEDGE_BASE_ID,
            index_version=INDEX_VERSION,
        )

    total_entities = total_relations = 0
    for row in graph_rows:
        source = _source_name(row["source_file"])
        document = chunks_by_source.get(source)
        if not document:
            continue
        document_id = int(document["document_id"])
        entities = []
        for item in row["entities"]:
            mapped = entity_mapping.get(item["entity_id"], {})
            chunk_id = mapped.get("milvus_chunk_id")
            if not chunk_id:
                continue
            entities.append(GraphEntity(item["entity_id"], item["entity_type"], item["name"], USER_ID, KNOWLEDGE_BASE_ID, document_id, INDEX_VERSION, chunk_id, confidence=float(item.get("confidence", 1.0))))
        entity_ids = {entity.entity_id for entity in entities}
        relations = []
        for item in row["relations"]:
            if item["source_entity_id"] not in entity_ids or item["target_entity_id"] not in entity_ids:
                continue
            mapped = source_mapping.get((source, item.get("source_chunk_id")), {})
            chunk_id = mapped.get("milvus_chunk_id") or next((entity.source_chunk_id for entity in entities if entity.entity_id == item["source_entity_id"]), "")
            if not chunk_id:
                continue
            relations.append(GraphRelation(item["relation_id"], item["relation_type"], item["source_entity_id"], item["target_entity_id"], USER_ID, KNOWLEDGE_BASE_ID, document_id, INDEX_VERSION, chunk_id, confidence=float(item.get("confidence", 1.0))))
        repository.replace_version(document_id, INDEX_VERSION, entities, relations)
        total_entities += len(entities)
        total_relations += len(relations)
    driver.close()
    print(json.dumps({"documents": len(graph_rows), "entities": total_entities, "relations": total_relations, "user_id": USER_ID, "knowledge_base_id": KNOWLEDGE_BASE_ID, "index_version": INDEX_VERSION}, ensure_ascii=False))


if __name__ == "__main__":
    main()
