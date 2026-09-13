"""真实 LLM 意图识别、受控路由和 Graph/Vector 检索端到端评估。"""

import argparse
import json
import time
from pathlib import Path
from statistics import mean

import yaml

from familyos_agent.clients.bge_m3 import BGEM3EmbeddingClient
from familyos_agent.graph_rag.llm_client import SyncOpenAIModel
from familyos_agent.graph_rag import ControlledRetriever, GraphRetriever, LLMIntentClassifier, Neo4jGraphRepository
from familyos_agent.retrieval import MilvusHybridRetriever
from familyos_agent.repositories import MySQLRepository


ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "evaluation/datasets/labels/queries.jsonl"
CONFIG = ROOT / "config/config.yaml"
OUT = Path(__file__).resolve().parent / "end_to_end_report.md"
DETAILS = Path(__file__).resolve().parent / "end_to_end_results.jsonl"
USER_ID = KNOWLEDGE_BASE_ID = 900001
INDEX_VERSION = 1


def _metric(ranked, positives, k):
    """按旧评估口径计算至少命中一个正样本的 Recall@K 和 MRR@K。"""
    expected = set(positives)
    recall = float(bool(set(ranked[:k]) & expected)) if expected else 0.0
    mrr = 0.0
    for rank, value in enumerate(ranked[:k], 1):
        if value in expected:
            mrr = 1.0 / rank
            break
    return recall, mrr


def _ids_from_graph(rows):
    """从 Neo4j 关系记录提取去重后的 canonical chunk/document 排名。"""
    chunks, documents = [], []
    for row in rows:
        for value in row.values():
            props = dict(value.items()) if hasattr(value, "items") else value if isinstance(value, dict) else {}
            chunk_id = str(props.get("source_chunk_id", ""))
            document_id = props.get("document_id")
            if chunk_id and chunk_id not in chunks:
                chunks.append(chunk_id)
            if document_id is not None and int(document_id) not in documents:
                documents.append(int(document_id))
    return chunks, documents


def main() -> None:
    """执行真实 LLM 路由和检索，并生成端到端指标报告。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="仅运行前 N 条，0 表示全部")
    args = parser.parse_args()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    extraction = config["graph_extraction"]
    model = SyncOpenAIModel(extraction["base_url"], extraction["api_key"], extraction["model"], float(extraction["timeout"].rstrip("s")), int(extraction["max_tokens"]))
    embedding = BGEM3EmbeddingClient(config["rag"]["embedding"]["model_name"], int(config["rag"]["embedding"]["batch_size"]), bool(config["rag"]["embedding"]["use_fp16"]), config["rag"]["embedding"]["device"])
    from pymilvus import MilvusClient
    client = MilvusClient(uri=config["rag"]["milvus"]["uri"], db_name=config["rag"]["milvus"]["database"], token=config["rag"]["milvus"].get("token") or None)
    vector = MilvusHybridRetriever(client, "familyos_document_chunks_eval_v1", embedding, int(config["rag"]["embedding"]["dimensions"]), int(config["rag"]["milvus"].get("rrf_k", 60)), int(config["rag"]["milvus"].get("candidate_limit", 50)))
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "familyos_dev"))
    driver.verify_connectivity()
    graph = GraphRetriever(Neo4jGraphRepository(driver), MySQLRepository(config["database"]["dsn"]).resolve_chunks)
    classifier = LLMIntentClassifier(model).classify
    controlled = ControlledRetriever(vector, graph, timeout=5.0, intent_classifier=classifier)
    labels = [json.loads(line) for line in LABELS.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit > 0:
        labels = labels[:args.limit]
    route_counts, route_metrics = {}, {}
    details = []
    for label in labels:
        started = time.perf_counter()
        error = ""
        plan = None
        try:
            result = controlled.retrieve(label["query"], USER_ID, KNOWLEDGE_BASE_ID, INDEX_VERSION, top_k=20)
            plan = result.get("retrieval_plan")
            route = result.get("route_strategy", "error")
            entities = list(plan.graph_plan.source_entities) if plan is not None and plan.graph_plan is not None else []
            confidence = 0.0
            chunks, documents = [], []
            for row in result.get("documents", []):
                if isinstance(row, dict):
                    chunk_id = row.get("chunk_id", row.get("source_chunk_id"))
                    document_id = row.get("document_id")
                else:
                    chunk_id = getattr(row, "chunk_id", getattr(row, "source_chunk_id", None))
                    document_id = getattr(row, "document_id", None)
                if chunk_id and str(chunk_id) not in chunks:
                    chunks.append(str(chunk_id))
                if document_id is not None and int(document_id) not in documents:
                    documents.append(int(document_id))
        except Exception as exc:
            route, entities, confidence, chunks, documents, error = "error", [], 0.0, [], [], "%s:%s" % (type(exc).__name__, str(exc)[:120])
        elapsed = (time.perf_counter() - started) * 1000
        route_counts[route] = route_counts.get(route, 0) + 1
        bucket = route_metrics.setdefault(route, {"chunk": {5: [], 10: [], 20: []}, "document": {5: [], 10: [], 20: []}, "chunk_mrr": [], "document_mrr": []})
        for k in (5, 10, 20):
            cr, cm = _metric(chunks, label.get("positive_chunks", []), k)
            dr, dm = _metric(documents, label.get("positive_documents", []), k)
            bucket["chunk"][k].append(cr); bucket["document"][k].append(dr)
            if k == 10:
                bucket["chunk_mrr"].append(cm); bucket["document_mrr"].append(dm)
        details.append({"query_id": label["query_id"], "route": route, "source_entities": entities, "confidence": confidence, "retrieval_plan": {"route": plan.route, "vector_query": plan.vector_query} if 'plan' in locals() and plan is not None else {}, "chunk_ids": chunks, "document_ids": documents, "latency_ms": elapsed, "error": error})
    DETAILS.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in details) + "\n", encoding="utf-8")
    lines = ["# LLM 意图识别 + 受控路由端到端评估", "", f"- 查询数：{len(labels)}", "- LLM：真实调用当前 graph_extraction 配置模型", "- Neo4j 命名空间：900001/900001/1", "- Milvus Collection：`familyos_document_chunks_eval_v1`", "", "## 路由分布", ""]
    lines.extend(f"- {route}: {count}" for route, count in sorted(route_counts.items()))
    lines.extend(["", "## 按路由检索指标", "", "| 路由 | Chunk R@10 | Chunk MRR@10 | Document R@10 | Document MRR@10 |", "|---|---:|---:|---:|---:|"])
    for route, bucket in sorted(route_metrics.items()):
        avg = lambda values: mean(values) if values else 0.0
        lines.append(f"| {route} | {avg(bucket['chunk'][10]):.4f} | {avg(bucket['chunk_mrr']):.4f} | {avg(bucket['document'][10]):.4f} | {avg(bucket['document_mrr']):.4f} |")
    lines.extend(["", "## 说明", "", "- 本报告的检索指标来自真实 LLM 路由后的实际结果，而不是预先知道正确路由。", "- 当前标签没有 `expected_route`，因此无法计算路由准确率；路由分布和逐 query 预测保存在 JSONL 明细中。", "- `tool` 路由未纳入本数据集，因为当前评估集没有真实库存/业务 Tool。", ""])
    OUT.write_text("\n".join(lines), encoding="utf-8")
    driver.close(); client.close(); embedding.close()
    print(OUT)


if __name__ == "__main__":
    main()
