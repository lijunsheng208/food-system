"""Run Dense, Sparse and native Milvus Hybrid retrieval evaluation."""

import argparse
import json
import math
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path

import yaml
from pymilvus import AnnSearchRequest, MilvusClient, RRFRanker, WeightedRanker

from familyos_agent.clients.bge_m3 import BGEM3EmbeddingClient
from familyos_agent.config import load_config


def ranked_ids(hits):
    """Read chunk and de-duplicated document ranking from Milvus hits."""
    chunks, documents = [], []
    for hit in hits:
        entity = hit.get("entity", hit)
        chunks.append(str(entity["chunk_id"]))
        document_id = int(entity["document_id"])
        if document_id not in documents:
            documents.append(document_id)
    return chunks, documents


def _normalise_number(value):
    return float(value) if value is not None else None


def _numeric_values(text, field):
    """Extract canonical values for one structured constraint field."""
    values = []
    if field == "minutes":
        def extract_duration(value_text):
            extracted = []
            combined = re.compile(r"(\d+(?:\.\d+)?)\s*小时\s*(\d+(?:\.\d+)?)\s*(分钟|分)", re.I)
            combined_values = [float(m.group(1)) * 60 + float(m.group(2)) for m in combined.finditer(value_text)]
            if combined_values:
                return combined_values
            pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(分钟|分|小时|h)", re.I)
            for match in pattern.finditer(value_text):
                value = float(match.group(1))
                if match.group(2) in ("小时", "h"):
                    value *= 60
                extracted.append(value)
            return extracted

        # The first imported chunk normally contains the recipe overview and
        # its total duration. Prefer that over short step-level durations.
        overview = text.split("## 必备原料和工具", 1)[0]
        values = extract_duration(overview) or extract_duration(text)
    elif field == "temperature_c":
        pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(?:℃|°C|摄氏度|度)", re.I)
        values.extend(float(match.group(1)) for match in pattern.finditer(text))
    elif field == "grams":
        pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(克|g|公斤|kg|斤)", re.I)
        for match in pattern.finditer(text):
            value = float(match.group(1))
            if match.group(2) in ("公斤", "kg"):
                value *= 1000
            elif match.group(2) == "斤":
                value *= 500
            values.append(value)
    elif field == "milliliters":
        pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(毫升|ml|升|l)", re.I)
        for match in pattern.finditer(text):
            value = float(match.group(1))
            if match.group(2) in ("升", "l"):
                value *= 1000
            values.append(value)
    elif field == "calories":
        pattern = re.compile(r"预估卡路里\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(?:大卡|千卡|卡路里)", re.I)
        values.extend(float(match.group(1)) for match in pattern.finditer(text))
    return values


def satisfies_numeric(text, constraints):
    """Return true when a document contains values satisfying all constraints."""
    for constraint in constraints:
        values = _numeric_values(text, constraint["field"])
        if not values:
            return False
        operator = constraint.get("operator", "eq")
        if operator == "eq":
            target = _normalise_number(constraint.get("value"))
            if target is None or not any(math.isclose(value, target, rel_tol=0.0, abs_tol=0.01) for value in values):
                return False
        elif operator == "<=":
            target = _normalise_number(constraint.get("value"))
            if target is None or not any(value <= target for value in values):
                return False
        elif operator == ">=":
            target = _normalise_number(constraint.get("value"))
            if target is None or not any(value >= target for value in values):
                return False
        elif operator == "between":
            low, high = float(constraint["min"]), float(constraint["max"])
            if not any(low <= value <= high for value in values):
                return False
        else:
            return False
    return True


def satisfies_query_constraints(query, document_text):
    forbidden = query.get("forbidden_terms", [])
    if forbidden and any(re.sub(r"\s+", "", term).lower() in re.sub(r"\s+", "", document_text).lower() for term in forbidden):
        return False
    constraints = query.get("numeric_constraints", [])
    return not constraints or satisfies_numeric(document_text, constraints)


def _constraint_rate(results, queries, document_contents):
    rates = []
    for query, result in zip(queries, results):
        if not query.get("forbidden_terms") and not query.get("numeric_constraints"):
            continue
        top_documents = result["documents"][:10]
        if not top_documents:
            rates.append(0.0)
            continue
        satisfied = sum(
            satisfies_query_constraints(query, document_contents.get(document_id, ""))
            for document_id in top_documents
        )
        rates.append(satisfied / len(top_documents))
    return sum(rates) / len(rates) if rates else 0.0


def metrics(results, queries, levels=(5, 10, 20), document_contents=None):
    """Compute retrieval, hard-negative ranking and constraint metrics."""
    document_contents = document_contents or {}
    if not queries:
        return {}
    output = {}
    for unit in ("chunk", "document"):
        positive_key = "positive_chunks" if unit == "chunk" else "positive_documents"
        for level in levels:
            output[f"{unit}_recall@{level}"] = sum(
                bool(set(query.get(positive_key, [])) & set(result[unit + "s"][:level]))
                for query, result in zip(queries, results)
            ) / len(queries)
        reciprocal_ranks, ndcgs = [], []
        for query, result in zip(queries, results):
            positives = set(query.get(positive_key, []))
            ranked = result[unit + "s"][:10]
            rank = next((index + 1 for index, value in enumerate(ranked) if value in positives), None)
            reciprocal_ranks.append(1 / rank if rank else 0.0)
            seen_relevant = set()
            dcg = 0.0
            for index, value in enumerate(ranked):
                if value in positives and value not in seen_relevant:
                    dcg += 1 / math.log2(index + 2)
                    seen_relevant.add(value)
            ideal = sum(1 / math.log2(index + 2) for index in range(min(len(positives), 10)))
            ndcgs.append(dcg / ideal if ideal else 0.0)
        output[f"{unit}_mrr@10"] = sum(reciprocal_ranks) / len(reciprocal_ranks)
        output[f"{unit}_ndcg@10"] = sum(ndcgs) / len(ndcgs)

    hard_negative_hits, first_ranks, mean_ranks = [], [], []
    for query, result in zip(queries, results):
        hard_negatives = set(query.get("hard_negative_documents", []))
        rank_by_document = {value: index + 1 for index, value in enumerate(result["documents"][:10])}
        ranks = [rank_by_document.get(document_id, 11) for document_id in hard_negatives]
        hard_negative_hits.append(any(rank <= 10 for rank in ranks))
        first_ranks.append(min(ranks) if ranks else 11)
        mean_ranks.append(sum(ranks) / len(ranks) if ranks else 11)
    output["hard_negative_hit@10"] = sum(hard_negative_hits) / len(hard_negative_hits)
    output["hard_negative_first_rank@10"] = sum(first_ranks) / len(first_ranks)
    output["hard_negative_mean_rank@10"] = sum(mean_ranks) / len(mean_ranks)
    output["constraint_satisfaction@10"] = _constraint_rate(results, queries, document_contents)
    output["constraint_query_count"] = sum(bool(q.get("forbidden_terms") or q.get("numeric_constraints")) for q in queries)
    return output


def evaluate_method(name, call, queries, document_contents=None):
    rows, latencies = [], []
    for index, query in enumerate(queries):
        started = time.perf_counter()
        hits = call(index)
        latencies.append((time.perf_counter() - started) * 1000)
        chunks, documents = ranked_ids(hits)
        rows.append({"query_id": query["query_id"], "chunks": chunks, "documents": documents})
    summary = metrics(rows, queries, document_contents=document_contents)
    ordered = sorted(latencies)
    summary.update({
        "latency_p50_ms": statistics.median(ordered),
        "latency_p95_ms": ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)],
    })
    return {"name": name, "summary": summary, "results": rows}


def _format_metric(value, key):
    if value is None:
        return "-"
    return f"{value:.2f}" if "latency" in key or "rank" in key else f"{value:.4f}"


def write_report(path, methods, queries, metadata):
    overall_keys = (
        "document_recall@5", "document_recall@10", "document_mrr@10", "document_ndcg@10",
        "chunk_recall@10", "hard_negative_hit@10", "hard_negative_first_rank@10",
        "hard_negative_mean_rank@10", "constraint_satisfaction@10", "latency_p95_ms",
    )
    lines = [
        "# Milvus 检索离线评估报告", "",
        f"- 查询数：{len(queries)}",
        f"- 来源菜谱数：{metadata.get('source_count', '-')}",
        f"- 来源类别数：{metadata.get('category_count', '-')}（{', '.join(metadata.get('categories', []))}）",
        f"- Collection：`{metadata['collection']}`",
        f"- 标签状态：`{metadata['label_status']}`", "",
        "## 总体对比", "",
        "| 方法 | Doc R@5 | Doc R@10 | Doc MRR@10 | Doc NDCG@10 | Chunk R@10 | HardNeg Hit@10 | HardNeg 首次排名 | HardNeg 平均排名 | 约束满足@10 | P95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method in methods:
        summary = method["summary"]
        lines.append("| %s | %s |" % (method["name"], " | ".join(_format_metric(summary.get(key), key) for key in overall_keys)))

    query_types = sorted({query.get("query_type", "unknown") for query in queries})
    lines += ["", "## 分 query_type 指标", "", "| 方法 | query_type | Doc R@10 | Doc MRR@10 | Doc NDCG@10 | Chunk R@10 | HardNeg 首次排名 | HardNeg 平均排名 | 约束满足@10 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for method in methods:
        for query_type in query_types:
            indexes = [index for index, query in enumerate(queries) if query.get("query_type") == query_type]
            subset_queries = [queries[index] for index in indexes]
            subset_results = [method["results"][index] for index in indexes]
            subset = metrics(subset_results, subset_queries, document_contents=metadata.get("document_contents", {}))
            constraint_value = (
                "-"
                if not subset.get("constraint_query_count")
                else _format_metric(subset.get("constraint_satisfaction@10"), "constraint_satisfaction@10")
            )
            lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                method["name"], query_type,
                _format_metric(subset.get("document_recall@10"), "document_recall@10"),
                _format_metric(subset.get("document_mrr@10"), "document_mrr@10"),
                _format_metric(subset.get("document_ndcg@10"), "document_ndcg@10"),
                _format_metric(subset.get("chunk_recall@10"), "chunk_recall@10"),
                _format_metric(subset.get("hard_negative_first_rank@10"), "hard_negative_first_rank@10"),
                _format_metric(subset.get("hard_negative_mean_rank@10"), "hard_negative_mean_rank@10"),
                constraint_value,
            ))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_queries(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_document_contents(path):
    contents = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            contents[int(row["document_id"])].append(row.get("content", ""))
    return {document_id: "\n".join(parts) for document_id, parts in contents.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--eval-config", default="evaluation/configs/retrieval_eval.yaml")
    parser.add_argument("--queries", default="evaluation/datasets/labels/queries.jsonl")
    parser.add_argument("--mapping", default="evaluation/datasets/raw/chunks.jsonl")
    parser.add_argument("--output", default="evaluation/reports/retrieval_eval.json")
    args = parser.parse_args()
    config = load_config(args.config)
    eval_config = yaml.safe_load(Path(args.eval_config).read_text(encoding="utf-8"))
    queries = _load_queries(Path(args.queries))
    document_contents = _load_document_contents(Path(args.mapping))
    embed = BGEM3EmbeddingClient(config.rag.embedding.model_name, config.rag.embedding.batch_size, config.rag.embedding.use_fp16, config.rag.embedding.device)
    vectors = embed.embed_documents([query["query"] for query in queries])
    embed.close()
    client = MilvusClient(uri=config.rag.milvus.uri, db_name=config.rag.milvus.database, token=config.rag.milvus.token or None, timeout=120)
    collection = eval_config["collection"]
    expression = f"user_id == {eval_config['user_id']} and knowledge_base_id == {eval_config['knowledge_base_id']} and index_version == {eval_config['index_version']} and active == true"
    limit = max(eval_config["top_k"])
    candidate_limit = eval_config["candidate_limit"]

    def dense(index):
        return client.search(collection_name=collection, data=[vectors.dense[index]], anns_field="dense_vector", filter=expression, limit=limit, output_fields=["chunk_id", "document_id"])[0]

    def sparse(index):
        return client.search(collection_name=collection, data=[vectors.sparse[index]], anns_field="sparse_vector", filter=expression, limit=limit, output_fields=["chunk_id", "document_id"])[0]

    def hybrid(index, ranker):
        requests = [
            AnnSearchRequest([vectors.dense[index]], "dense_vector", {"metric_type": "COSINE"}, candidate_limit, expr=expression),
            AnnSearchRequest([vectors.sparse[index]], "sparse_vector", {"metric_type": "IP"}, candidate_limit, expr=expression),
        ]
        return client.hybrid_search(collection, requests, ranker, limit=limit, output_fields=["chunk_id", "document_id"])[0]

    methods = [
        evaluate_method("dense", dense, queries, document_contents),
        evaluate_method("sparse", sparse, queries, document_contents),
    ]
    for k in eval_config["fusion"]["rrf_k"]:
        methods.append(evaluate_method(f"hybrid_rrf_k{k}", lambda index, k=k: hybrid(index, RRFRanker(k)), queries, document_contents))
    for dense_weight, sparse_weight in eval_config["fusion"]["weighted"]:
        methods.append(evaluate_method(f"hybrid_weighted_{dense_weight}_{sparse_weight}", lambda index, d=dense_weight, s=sparse_weight: hybrid(index, WeightedRanker(d, s)), queries, document_contents))
    client.close()

    metadata = {
        "collection": collection,
        "label_status": sorted({query.get("label_status", "") for query in queries}),
        "source_count": len({query.get("source") for query in queries}),
        "category_count": len({query.get("source_category") for query in queries}),
        "categories": sorted({query.get("source_category") for query in queries}),
        "document_contents": document_contents,
    }
    payload = {"metadata": {key: value for key, value in metadata.items() if key != "document_contents"}, "methods": methods}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(output.with_suffix(".md"), methods, queries, metadata)
    print(output)
    print(output.with_suffix(".md"))


if __name__ == "__main__":
    main()
