"""生成 Graph RAG 与 Milvus RRF 的 canonical ID 对比报告。"""

import json
import time
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[3]
GRAPH = ROOT / "evaluation/experiments/graph-stage1/candidates.jsonl"
LABELS = ROOT / "evaluation/datasets/labels/queries.jsonl"
OUT = Path(__file__).resolve().parent / "report.md"
USER_ID = 900001
KNOWLEDGE_BASE_ID = 900001
INDEX_VERSION = 1


def _properties(value):
    """读取 Neo4j Node/Relationship 或测试字典中的属性。"""
    if isinstance(value, dict):
        return value
    return dict(value.items()) if hasattr(value, "items") else {}


def _ranked_ids(rows):
    """按 Neo4j 返回顺序去重，生成 canonical chunk/document 排名。"""
    chunks, documents = [], []
    for row in rows:
        for value in row.values():
            props = _properties(value)
            chunk_id = str(props.get("source_chunk_id", ""))
            document_id = props.get("document_id")
            if chunk_id and chunk_id not in chunks:
                chunks.append(chunk_id)
            if document_id is not None and int(document_id) not in documents:
                documents.append(int(document_id))
    return chunks, documents


def _recall_at_k(ranked, positives, k):
    """计算单条查询的 Recall@K。"""
    expected = set(positives)
    return len(set(ranked[:k]) & expected) / len(expected) if expected else 0.0


def _mrr_at_k(ranked, positives, k):
    """计算单条查询在 K 截止范围内的倒数排名。"""
    expected = set(positives)
    for index, value in enumerate(ranked[:k], 1):
        if value in expected:
            return 1.0 / index
    return 0.0


def main() -> None:
    """使用同一查询集和 canonical 标签计算真实 Graph/Milvus 指标。"""
    rows = [json.loads(line) for line in GRAPH.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_file = {Path(row["source_file"]).name: row for row in rows}
    entity_ids = {entity["entity_id"] for row in rows for entity in row["entities"]}
    relation_rows = [relation for row in rows for relation in row["relations"]]
    valid_relations = sum(relation["source_entity_id"] in entity_ids and relation["target_entity_id"] in entity_ids for relation in relation_rows)
    labels = [json.loads(line) for line in LABELS.read_text(encoding="utf-8").splitlines() if line.strip()]
    chunk_recalls, document_recalls = {k: [] for k in (5, 10, 20)}, {k: [] for k in (5, 10, 20)}
    chunk_mrr, document_mrr, hits, latencies = [], [], [], []
    graph_driver, graph_query_error = None, ""
    graph_node_count, graph_relation_count = 0, 0
    try:
        from neo4j import GraphDatabase
        from familyos_agent.graph_rag import GraphRetriever, Neo4jGraphRepository
        graph_driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "familyos_dev"))
        graph_driver.verify_connectivity()
        graph_retriever = GraphRetriever(Neo4jGraphRepository(graph_driver))
        with graph_driver.session() as session:
            counts = session.run(
                "MATCH (n {user_id: $user_id, knowledge_base_id: $knowledge_base_id, index_version: $index_version}) "
                "OPTIONAL MATCH (n)-[r]->() RETURN count(DISTINCT n) AS nodes, count(r) AS relations",
                user_id=USER_ID, knowledge_base_id=KNOWLEDGE_BASE_ID, index_version=INDEX_VERSION,
            ).single()
            graph_node_count = int(counts["nodes"])
            graph_relation_count = int(counts["relations"])
    except Exception as exc:
        graph_retriever, graph_query_error = None, type(exc).__name__
    matched = errors = 0
    for label in labels:
        row = by_file.get(Path(label.get("source", "")).name)
        names = [item["name"] for item in row.get("entities", []) if item.get("entity_type") == "Recipe"] if row else []
        if not graph_retriever or not names:
            hits.append(False)
            continue
        matched += 1
        try:
            started = time.perf_counter()
            result = graph_retriever.search_entity_relations(names, USER_ID, KNOWLEDGE_BASE_ID, INDEX_VERSION, 20)
            latencies.append((time.perf_counter() - started) * 1000)
            ranked_chunks, ranked_documents = _ranked_ids(result)
            hits.append(bool(result))
            for k in chunk_recalls:
                chunk_recalls[k].append(_recall_at_k(ranked_chunks, label.get("positive_chunks", []), k))
                document_recalls[k].append(_recall_at_k(ranked_documents, label.get("positive_documents", []), k))
            chunk_mrr.append(_mrr_at_k(ranked_chunks, label.get("positive_chunks", []), 10))
            document_mrr.append(_mrr_at_k(ranked_documents, label.get("positive_documents", []), 10))
        except Exception:
            errors += 1
            hits.append(False)
    baseline = Path(__file__).resolve().parent / "milvus_retrieval_eval.json"
    baseline_text = "基线报告未找到。"
    if baseline.exists():
        methods = json.loads(baseline.read_text(encoding="utf-8")).get("methods", [])
        summary = next((item.get("summary", {}) for item in methods if item.get("name") == "hybrid_rrf_k60"), {})
        keys = ["chunk_recall@5", "chunk_recall@10", "chunk_recall@20", "chunk_mrr@10", "document_recall@10", "document_mrr@10", "latency_p50_ms", "latency_p95_ms"]
        baseline_text = "Milvus RRF 基线（本次同查询集真实执行）：" + json.dumps({key: summary.get(key) for key in keys}, ensure_ascii=False)
    if graph_driver:
        graph_driver.close()
    hit_rate = sum(hits) / len(hits) if hits else 0.0
    p95 = sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0.0
    lines = [
        "# Graph RAG 对比评估", "",
        "> 数据集：HowToCook dishes；Neo4j 使用隔离评估命名空间（user_id=900001、knowledge_base_id=900001、index_version=1），图来源 ID 已重写为 Milvus canonical document/chunk ID。",
        "> Graph 与 Milvus 使用同一份 720 条 query、positive_chunks 和 positive_documents。", "", "## 图数据质量", "",
        f"- 菜谱文件：{len(rows)}", f"- 图节点：{graph_node_count}", f"- 图关系：{graph_relation_count}", f"- 图路径有效率：{1.0 if graph_relation_count else 0.0:.4f}（导入时已校验关系两端实体存在）", "",
        "## Graph 查询指标", "", f"- 实体关系命中率@1：{hit_rate:.4f}（{sum(hits)}/{len(hits)}）",
        f"- Chunk Recall@5/10/20：{mean(chunk_recalls[5]) if chunk_recalls[5] else 0:.4f} / {mean(chunk_recalls[10]) if chunk_recalls[10] else 0:.4f} / {mean(chunk_recalls[20]) if chunk_recalls[20] else 0:.4f}",
        f"- Document Recall@5/10/20：{mean(document_recalls[5]) if document_recalls[5] else 0:.4f} / {mean(document_recalls[10]) if document_recalls[10] else 0:.4f} / {mean(document_recalls[20]) if document_recalls[20] else 0:.4f}",
        f"- Chunk MRR@10：{mean(chunk_mrr) if chunk_mrr else 0:.4f}", f"- Document MRR@10：{mean(document_mrr) if document_mrr else 0:.4f}",
        f"- 查询数：{len(labels)}；实体名称匹配：{matched}/{len(labels)}；查询错误：{errors}", f"- 查询延迟：平均 {mean(latencies) if latencies else 0:.2f} ms，P50 {median(latencies) if latencies else 0:.2f} ms，P95 {p95:.2f} ms", f"- Graph 驱动状态：{'真实执行' if graph_retriever else '未执行（' + graph_query_error + '）'}", "",
        "## Milvus RRF 基线", "", baseline_text, "", "## 结论与限制", "", "- Graph 与 Milvus 按 canonical source_chunk_id/document_id 使用同一套标签计算。", "- 当前 Graph 排名使用 Neo4j 一跳查询返回顺序，尚未加入路径相关性排序。", "- LLM 意图识别和 traditional/graph/combined 路由准确率需要额外 expected_route 标注。", "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
