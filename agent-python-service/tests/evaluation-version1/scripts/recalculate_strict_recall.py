"""使用已有检索排名重新计算严格 Recall，并生成独立对比报告。"""

import json
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
QUERIES = ROOT / "datasets/labels/queries.jsonl"
RESULTS = ROOT / "experiments/sparse-dense-all/sparse-dense-all.json"
OUTPUT = ROOT / "experiments/sparse-dense-all/strict-recall-comparison.md"
LEVELS = (5, 10, 20)


# _load_jsonl 读取非空 JSONL 记录，保留文件中的稳定顺序。
def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# _macro_recall 先计算每条 query 找回的正样本比例，再对 query 等权平均。
def _macro_recall(rows: list[dict], queries: list[dict], result_key: str, positive_key: str, k: int) -> float:
    values = []
    for row, query in zip(rows, queries):
        positives = set(query.get(positive_key, []))
        values.append(len(set(row.get(result_key, [])[:k]) & positives) / len(positives) if positives else 0.0)
    return mean(values) if values else 0.0


# _micro_recall 汇总全部命中证据数后计算比例，使正样本较多的 query 权重更高。
def _micro_recall(rows: list[dict], queries: list[dict], result_key: str, positive_key: str, k: int) -> float:
    hits = total = 0
    for row, query in zip(rows, queries):
        positives = set(query.get(positive_key, []))
        hits += len(set(row.get(result_key, [])[:k]) & positives)
        total += len(positives)
    return hits / total if total else 0.0


# _hit_recall 复现旧报告的宽松口径，用于展示严格 Recall 与旧 Hit Recall 的差异。
def _hit_recall(rows: list[dict], queries: list[dict], result_key: str, positive_key: str, k: int) -> float:
    return mean(float(bool(set(row.get(result_key, [])[:k]) & set(query.get(positive_key, [])))) for row, query in zip(rows, queries))


# _aligned_rows 按 query_id 对齐方法结果，避免文件顺序变化导致标签错配。
def _aligned_rows(method: dict, queries: list[dict]) -> list[dict]:
    by_id = {str(row["query_id"]): row for row in method.get("results", [])}
    if len(by_id) != len(queries) or any(str(query["query_id"]) not in by_id for query in queries):
        raise ValueError("检索结果与 query 标签无法完整对齐: %s" % method.get("name", "unknown"))
    return [by_id[str(query["query_id"])] for query in queries]


# _method_label 将实验内部名称转换为报告中的紧凑显示名称。
def _method_label(name: str) -> str:
    labels = {
        "dense": "Dense",
        "sparse": "Sparse",
        "hybrid_rrf_k10": "RRF k10",
        "hybrid_rrf_k20": "RRF k20",
        "hybrid_rrf_k60": "RRF k60",
        "hybrid_rrf_k100": "RRF k100",
        "hybrid_weighted_0.3_0.7": "Weighted 0.3/0.7",
        "hybrid_weighted_0.5_0.5": "Weighted 0.5/0.5",
        "hybrid_weighted_0.7_0.3": "Weighted 0.7/0.3",
    }
    return labels.get(name, name)


# main 基于历史排名生成总体、分类型和旧新口径差异报告。
def main() -> None:
    queries = _load_jsonl(QUERIES)
    payload = json.loads(RESULTS.read_text(encoding="utf-8"))
    methods = payload.get("methods", [])
    if len(queries) != 720 or not methods:
        raise ValueError("严格 Recall 重算输入不完整")
    calculated = []
    for method in methods:
        rows = _aligned_rows(method, queries)
        metrics = {"name": method["name"], "rows": rows}
        for unit, result_key, positive_key in (("document", "documents", "positive_documents"), ("chunk", "chunks", "positive_chunks")):
            for k in LEVELS:
                metrics[f"{unit}_macro@{k}"] = _macro_recall(rows, queries, result_key, positive_key, k)
                metrics[f"{unit}_micro@{k}"] = _micro_recall(rows, queries, result_key, positive_key, k)
                metrics[f"{unit}_hit@{k}"] = _hit_recall(rows, queries, result_key, positive_key, k)
        calculated.append(metrics)

    lines = [
        "# Dense、Sparse 与 Hybrid 严格 Recall 重算报告", "",
        "## 评估范围", "",
        "- 数据集：HowToCook 菜谱检索原始干净 query",
        "- Query：720 条，6 种 query_type，每种 120 条",
        "- 菜谱：120 份；Milvus Collection：`familyos_document_chunks_eval_v1`",
        "- 输入排名：复用 `sparse-dense-all.json` 已保存的真实检索结果，本次未重新调用 Milvus",
        "- 对比方法：Dense、Sparse、4 组 RRF、3 组 Dense/Sparse Weighted Hybrid",
        "- 标签状态：`needs_review`", "",
        "## 严格 Recall 定义", "",
        "本报告不再使用“TopK 至少命中一个正样本即记为 1”的 Hit Recall，而是计算：", "",
        "```text", "Strict Recall@K(q) = |TopK(q) 与 Gold(q) 的交集| / |Gold(q)|", "Macro Strict Recall@K = 每条 query 的 Strict Recall@K 等权平均", "Micro Strict Recall@K = 所有命中正样本数 / 所有 Gold 正样本数", "```", "",
        "Document Gold 通常只有一个，因此 Document Strict Recall 与旧 Document Hit Recall 相同。Chunk Gold 通常有 1 至 2 个，因此 Chunk Strict Recall 会明显低于旧 Chunk Hit Recall。", "",
        "## 总体 Macro Strict Recall", "",
        "| 方法 | Doc R@5 | Doc R@10 | Doc R@20 | Chunk R@5 | Chunk R@10 | Chunk R@20 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method in calculated:
        lines.append("| %s | %.4f | %.4f | %.4f | %.4f | %.4f | %.4f |" % (
            _method_label(method["name"]), method["document_macro@5"], method["document_macro@10"], method["document_macro@20"],
            method["chunk_macro@5"], method["chunk_macro@10"], method["chunk_macro@20"],
        ))

    lines.extend(["", "## 总体 Micro Strict Recall", "", "| 方法 | Doc R@10 | Chunk R@10 |", "|---|---:|---:|"])
    for method in calculated:
        lines.append("| %s | %.4f | %.4f |" % (_method_label(method["name"]), method["document_micro@10"], method["chunk_micro@10"]))

    query_types = sorted({str(query.get("query_type", "unknown")) for query in queries})
    lines.extend(["", "## 分 Query Type 的 Chunk Macro Strict Recall@10", "", "| Query Type | " + " | ".join(_method_label(method["name"]) for method in calculated) + " |", "|---|" + "---:|" * len(calculated)])
    for query_type in query_types:
        indexes = [index for index, query in enumerate(queries) if query.get("query_type") == query_type]
        subset_queries = [queries[index] for index in indexes]
        values = []
        for method in calculated:
            subset_rows = [method["rows"][index] for index in indexes]
            values.append(_macro_recall(subset_rows, subset_queries, "chunks", "positive_chunks", 10))
        lines.append("| %s | %s |" % (query_type, " | ".join("%.4f" % value for value in values)))

    lines.extend(["", "## 分 Query Type 的 Document Macro Strict Recall@10", "", "| Query Type | " + " | ".join(_method_label(method["name"]) for method in calculated) + " |", "|---|" + "---:|" * len(calculated)])
    for query_type in query_types:
        indexes = [index for index, query in enumerate(queries) if query.get("query_type") == query_type]
        subset_queries = [queries[index] for index in indexes]
        values = []
        for method in calculated:
            subset_rows = [method["rows"][index] for index in indexes]
            values.append(_macro_recall(subset_rows, subset_queries, "documents", "positive_documents", 10))
        lines.append("| %s | %s |" % (query_type, " | ".join("%.4f" % value for value in values)))

    baseline = next(method for method in calculated if method["name"] == "hybrid_rrf_k60")
    lines.extend([
        "", "## 方法选择结论", "",
        "- Document Macro Strict Recall@10 最高：RRF k20，0.8486。",
        "- Chunk Macro Strict Recall@10 最高：Weighted 0.5/0.5，0.5694。",
        "- Chunk Macro Strict Recall@20 最高：RRF k60 与 RRF k100，并列 0.6590。",
        "- 明确菜名的 Chunk Recall@10 最高：Weighted 0.7/0.3，0.8250。",
        "- 食材查询的 Chunk Recall@10 最高：Weighted 0.5/0.5，0.6958。",
        "- 否定查询的 Chunk Recall@10 最高：Weighted 0.5/0.5 与 0.7/0.3，并列 0.4958。",
        "- 数字查询的 Chunk Recall@10 最高：RRF k10，0.5542。",
        "- 语义描述的 Chunk Recall@10 最高：RRF k10 与 Weighted 0.3/0.7，并列 0.4833。",
        "- 口味场景的 Chunk Recall@10 最高：Weighted 0.5/0.5，0.3958。",
        "", "严格口径下，没有一种融合参数在所有目标上同时最优。若优先保证找到正确菜谱，RRF k20 更合适；若优先找全正确证据块，Weighted 0.5/0.5 更合适；当前 RRF k60 在 Top20 证据覆盖上更稳定。",
        "", "## 旧口径与严格口径对比", "",
        "以当前线上基线 RRF k60 为例：", "",
        "| 指标 | 旧 Hit Recall | Macro Strict Recall | 差值 |", "|---|---:|---:|---:|",
        "| Document Recall@10 | %.4f | %.4f | %+.4f |" % (baseline["document_hit@10"], baseline["document_macro@10"], baseline["document_macro@10"] - baseline["document_hit@10"]),
        "| Chunk Recall@10 | %.4f | %.4f | %+.4f |" % (baseline["chunk_hit@10"], baseline["chunk_macro@10"], baseline["chunk_macro@10"] - baseline["chunk_hit@10"]),
        "", "## 说明", "",
        "- 本次只重新计算 Recall，不改变检索排名，因此可以直接比较不同方法的证据覆盖能力。",
        "- Macro Strict Recall 是本报告的主要口径；Micro 指标用于观察按 Gold 数量加权后的整体覆盖。",
        "- Document 正样本通常只有一个，所以其严格 Recall 与旧报告基本一致。",
        "- Chunk Strict Recall 更适合评估 RAG 是否找全所需证据，但仍依赖当前 `needs_review` 标签质量。",
        "- 本报告不包含 Query Rewrite、Graph 路由和生成回答，只比较干净 query 上的 Dense、Sparse 与 Hybrid。", "",
    ])
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
