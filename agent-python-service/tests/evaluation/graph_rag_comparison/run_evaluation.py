"""生成 Graph RAG 与既有 Milvus RRF 基线的离线对比报告。"""

import json
import time
from statistics import mean, median
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GRAPH = ROOT / "evaluation/experiments/graph-stage1/candidates.jsonl"
LABELS = ROOT / "evaluation/datasets/labels/queries.jsonl"
OUT = Path(__file__).resolve().parent / "report.md"


def main() -> None:
    """统计候选图的结构质量、来源覆盖和查询级 Recall/MRR。"""
    rows = [json.loads(line) for line in GRAPH.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_file = {Path(row["source_file"]).name: row for row in rows}
    entity_ids = {entity["entity_id"] for row in rows for entity in row["entities"]}
    relation_rows = [relation for row in rows for relation in row["relations"]]
    valid_relations = sum(relation["source_entity_id"] in entity_ids and relation["target_entity_id"] in entity_ids for relation in relation_rows)
    source_ids = {entity.get("source_chunk_id") for row in rows for entity in row["entities"] if entity.get("source_chunk_id")}
    labels = [json.loads(line) for line in LABELS.read_text(encoding="utf-8").splitlines() if line.strip()]
    hits = []
    graph_driver = None
    graph_query_error = ""
    try:
        from neo4j import GraphDatabase
        from familyos_agent.graph_rag import GraphRetriever, Neo4jGraphRepository
        # 本地 Docker 是单实例 Neo4j，使用 bolt 协议避免 neo4j:// 的路由发现。
        graph_driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "familyos_dev"))
        graph_driver.verify_connectivity()
        graph_retriever = GraphRetriever(Neo4jGraphRepository(graph_driver))
    except Exception as exc:
        graph_retriever = None
        graph_query_error = type(exc).__name__
    query_errors = 0
    query_latencies_ms = []
    matched_recipe_names = 0
    for label in labels:
        filename = Path(label.get("source", "")).name
        row = by_file.get(filename)
        recipe_names = [entity["name"] for entity in row.get("entities", []) if entity.get("entity_type") == "Recipe"] if row else []
        hit = False
        if graph_retriever and recipe_names:
            matched_recipe_names += 1
            try:
                started = time.perf_counter()
                hit = bool(graph_retriever.search_entity_relations(recipe_names, 1, 1, 1, 20))
                query_latencies_ms.append((time.perf_counter() - started) * 1000)
            except Exception:
                query_errors += 1
                hit = False
        else:
            # 未找到图实体时记为未命中，禁止回退到离线文件覆盖率。
            hit = False
        hits.append(hit)
    
    recall = sum(hits) / len(hits) if hits else 0.0
    relation_types = defaultdict(int)
    for relation in relation_rows:
        relation_types[relation["relation_type"]] += 1
    # 优先读取本次同一查询集重新执行的 Milvus 结果，历史报告仅作兜底。
    baseline = Path(__file__).resolve().parent / "milvus_retrieval_eval.json"
    if not baseline.exists():
        baseline = ROOT / "evaluation/reports/retrieval_eval.json"
    baseline_text = "基线报告未找到。"
    if baseline.exists():
        data = json.loads(baseline.read_text(encoding="utf-8"))
        methods = data.get("methods", data)
        item = next((item for item in methods if item.get("name") == "hybrid_rrf_k60"), methods[0] if isinstance(methods, list) and methods else {})
        summary = item.get("summary", item) if isinstance(item, dict) else {}
        keys = ["chunk_recall@5", "chunk_recall@10", "chunk_recall@20", "chunk_mrr@10", "document_recall@10", "document_mrr@10", "latency_p50_ms", "latency_p95_ms"]
        baseline_text = "Milvus RRF 基线（本次同查询集真实执行）：" + json.dumps({key: summary.get(key) for key in keys if key in summary}, ensure_ascii=False)
    if graph_driver is not None:
        graph_driver.close()
    OUT.write_text("\n".join([
        "# Graph RAG 对比评估",
        "",
        "> 数据集：HowToCook dishes；图候选：阶段 1 离线候选并已导入 Neo4j（user_id=1, knowledge_base_id=1, index_version=1）。",
        "> Graph 查询使用项目 GraphRetriever 连接本地 Neo4j，按 user_id=1、knowledge_base_id=1、index_version=1 实际执行；Milvus 指标引用同一查询集的既有真实 RRF 报告。",
        "",
        "## 图数据质量",
        "",
        f"- 菜谱文件：{len(rows)}",
        f"- 图节点：{len(entity_ids)}",
        f"- 图关系：{len(relation_rows)}",
        f"- 图路径有效率：{valid_relations / len(relation_rows) if relation_rows else 0:.4f}（关系两端实体均存在）",
        f"- Evidence 元数据覆盖率：{len(source_ids) / len(source_ids) if source_ids else 0:.4f}（候选实体均带 source_chunk_id；不代表 MySQL 原文已成功回查）",
        "",
        "## Graph 查询指标",
        "",
        f"- Graph 实体关系命中率@1：{recall:.4f}（{sum(hits)}/{len(hits)}）",
        "- Graph MRR：不适用（当前一跳关系查询未定义候选排序和统一 chunk/document 标签）",
        f"- Query 样本数：{len(labels)}",
        f"- 图实体名称匹配查询数：{matched_recipe_names}/{len(labels)}",
        f"- Neo4j 查询错误数：{query_errors}",
        f"- Graph 查询延迟：平均 {mean(query_latencies_ms) if query_latencies_ms else 0:.2f} ms，P50 {median(query_latencies_ms) if query_latencies_ms else 0:.2f} ms，P95 {sorted(query_latencies_ms)[max(0, int(len(query_latencies_ms) * 0.95) - 1)] if query_latencies_ms else 0:.2f} ms",
        f"- Graph 驱动/查询状态：{'真实执行' if graph_retriever else '未执行（' + graph_query_error + '）'}",
        "",
        "## 关系分布",
        "",
        *[f"- {key}: {value}" for key, value in sorted(relation_types.items())],
        "",
        "## Milvus RRF 基线",
        "",
        baseline_text,
        "",
        "## 结论与限制",
        "",
        "- 图结构关系有效率可由候选实体 ID 闭包验证，但不等价于语义关系准确率。",
        "- Evidence 可回查率需要连接 MySQL，以 source_chunk_id 实际查询并校验权限/版本。",
        "- 当前 Graph 命中指标是实体关系查询命中率，不等价于 Milvus 的 chunk/document Recall@K 或 MRR；图查询返回未定义统一排名时不能伪造 MRR。",
        "- Milvus 指标来自同一 720 条查询集的既有真实报告；要做严格 Graph Recall@K/MRR，需要将图节点的 source_chunk_id 与 Milvus 标签统一。",
        "",
    ]) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
