"""基于已完成的端到端明细，按旧评估口径重新生成对比报告。"""

import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "evaluation/datasets/labels/queries.jsonl"
DIRECTORY = Path(__file__).resolve().parent
DETAILS = DIRECTORY / "end_to_end_results.jsonl"
BASELINE = DIRECTORY / "milvus_retrieval_eval.json"
OUT = DIRECTORY / "end_to_end_report.md"


def _metrics(rows, labels):
    """使用旧评估的 Hit Recall 与 MRR 定义计算一组查询指标。"""
    result = {}
    for unit, result_key, positive_key in (("chunk", "chunk_ids", "positive_chunks"), ("document", "document_ids", "positive_documents")):
        for k in (5, 10, 20):
            result[f"{unit}_recall@{k}"] = sum(bool(set(row[result_key][:k]) & set(label[positive_key])) for row, label in zip(rows, labels)) / len(rows)
        reciprocal = []
        for row, label in zip(rows, labels):
            positives = set(label[positive_key])
            rank = next((index for index, value in enumerate(row[result_key][:10], 1) if value in positives), None)
            reciprocal.append(1.0 / rank if rank else 0.0)
        result[f"{unit}_mrr@10"] = statistics.mean(reciprocal)
    return result


def main():
    """校验查询对应关系，并输出当前完整流程与旧 RRF 的同口径结果。"""
    labels = [json.loads(line) for line in LABELS.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [json.loads(line) for line in DETAILS.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != len(labels) or any(row["query_id"] != label["query_id"] for row, label in zip(rows, labels)):
        raise ValueError("端到端结果与查询标签不一致")
    current = _metrics(rows, labels)
    methods = json.loads(BASELINE.read_text(encoding="utf-8"))["methods"]
    baseline_method = next(item for item in methods if item["name"] == "hybrid_rrf_k60")
    baseline = baseline_method["summary"]
    baseline_rows = {row["query_id"]: row for row in baseline_method["results"]}
    vector_rows = [row for row in rows if row["route"] == "vector"]
    exact_vector_rankings = sum(row["chunk_ids"] == baseline_rows[row["query_id"]]["chunks"] for row in vector_rows)
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    current["latency_p50_ms"] = statistics.median(latencies)
    current["latency_p95_ms"] = latencies[math.ceil(len(latencies) * 0.95) - 1]
    routes = {}
    for route in sorted({row["route"] for row in rows}):
        indexes = [index for index, row in enumerate(rows) if row["route"] == route]
        routes[route] = _metrics([rows[index] for index in indexes], [labels[index] for index in indexes])
        routes[route]["count"] = len(indexes)
    keys = ("chunk_recall@5", "chunk_recall@10", "chunk_recall@20", "chunk_mrr@10", "document_recall@5", "document_recall@10", "document_recall@20", "document_mrr@10")
    names = {"chunk_recall@5": "Chunk Recall@5", "chunk_recall@10": "Chunk Recall@10", "chunk_recall@20": "Chunk Recall@20", "chunk_mrr@10": "Chunk MRR@10", "document_recall@5": "Document Recall@5", "document_recall@10": "Document Recall@10", "document_recall@20": "Document Recall@20", "document_mrr@10": "Document MRR@10"}
    lines = [
        "# LLM 意图识别 + 受控路由端到端评估", "",
        "- 查询数：720", "- LLM：真实调用当前 graph_extraction 配置模型",
        "- Vector：原始 query + Milvus 原生 hybrid_search + RRFRanker(60) + 每路 50 候选",
        "- Neo4j 命名空间：900001/900001/1", "- Milvus Collection：`familyos_document_chunks_eval_v1`",
        "- 错误数：%d" % sum(bool(row.get("error")) for row in rows),
        f"- Vector 完整排名与旧 RRF 逐条一致：{exact_vector_rankings}/{len(vector_rows)}", "", "## 总体对比", "",
        "| 指标 | 旧 Milvus RRF | 当前完整流程 | 变化 |", "|---|---:|---:|---:|",
    ]
    for key in keys:
        lines.append(f"| {names[key]} | {baseline[key]:.4f} | {current[key]:.4f} | {current[key] - baseline[key]:+.4f} |")
    lines.extend(["", "## 路由分布与指标", "", "| 路由 | 数量 | Chunk R@10 | Chunk MRR@10 | Document R@10 | Document MRR@10 |", "|---|---:|---:|---:|---:|---:|"])
    for route, values in routes.items():
        lines.append(f"| {route} | {values['count']} | {values['chunk_recall@10']:.4f} | {values['chunk_mrr@10']:.4f} | {values['document_recall@10']:.4f} | {values['document_mrr@10']:.4f} |")
    lines.extend([
        "", "## 延迟", "", f"- 当前完整流程 P50：{current['latency_p50_ms']:.2f} ms",
        f"- 当前完整流程 P95：{current['latency_p95_ms']:.2f} ms", f"- 旧评估 Milvus P95：{baseline['latency_p95_ms']:.2f} ms",
        "- 当前延迟包含逐条真实 LLM 意图识别和查询 Embedding；旧延迟只统计预编码后的 Milvus 查询，两者不属于同一耗时口径。",
        "", "## 说明", "", "- Recall 使用旧评估定义：Top-K 中至少出现一个正样本即记为 1。",
        "- 当前标签没有 expected_route，因此无法计算路由准确率。", "- 逐查询预测、计划、结果 ID 和耗时保存在 end_to_end_results.jsonl。", "",
    ])
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
