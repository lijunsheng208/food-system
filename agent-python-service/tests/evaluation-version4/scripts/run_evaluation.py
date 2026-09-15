"""运行不经过 Agent 和回答模型的 V4 菜谱检索离线评测。"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence

import yaml
from pymilvus import AnnSearchRequest, MilvusClient, RRFRanker

from familyos_agent.clients.bge_m3 import BGEM3EmbeddingClient
from familyos_agent.config import load_config
from familyos_agent.retrieval import BGEChunkReranker, DashScopeReranker, EmbeddedChunks


EVALUATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EVALUATION_ROOT))

from lib.metrics import evaluate_retrieval  # noqa: E402


CORE_METHODS = ("dense", "sparse", "hybrid_rrf", "hybrid_parent", "hybrid_parent_rerank")


# _load_jsonl 读取非空 JSONL 记录。
def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# _attach_chunk_gold 按 query_id 关联独立 Chunk qrels，并拒绝证据 Query 缺失 Gold。
def _attach_chunk_gold(
    queries: Sequence[Dict[str, Any]],
    chunk_gold: Sequence[Mapping[str, Any]],
) -> None:
    gold_by_query_id = {str(item["query_id"]): dict(item) for item in chunk_gold}
    if len(gold_by_query_id) != len(chunk_gold):
        raise ValueError("Chunk Gold query_id 不唯一")
    missing = [
        str(query["query_id"])
        for query in queries
        if query.get("evidence_groups") and str(query["query_id"]) not in gold_by_query_id
    ]
    if missing:
        raise ValueError(f"证据 Query 缺少 Chunk Gold：{missing[:3]}")
    for query in queries:
        gold = gold_by_query_id.get(str(query["query_id"]))
        if gold is not None:
            query["chunk_gold"] = gold


# _entity 将不同 pymilvus 返回形态统一为普通字典。
def _entity(hit: Any) -> Dict[str, Any]:
    if isinstance(hit, Mapping):
        entity = hit.get("entity", hit)
        return dict(entity or {})
    return dict(getattr(hit, "entity", {}) or {})


# _score 读取 Milvus 检索分数；Parent 扩展行没有初始分数时返回 None。
def _score(hit: Any) -> float | None:
    if isinstance(hit, Mapping):
        value = hit.get("distance", hit.get("score"))
    else:
        value = getattr(hit, "distance", None)
    return float(value) if value is not None else None


# _result_item 将命中记录转成 V4 指标模块需要的稳定字段。
def _result_item(hit: Any, override_score: float | None = None) -> Dict[str, Any]:
    entity = _entity(hit)
    score = override_score if override_score is not None else _score(hit)
    return {
        "chunk_id": str(entity["chunk_id"]),
        "parent_id": str(entity.get("parent_id", "")),
        "document_id": int(entity["document_id"]),
        "chunk_index": int(entity.get("chunk_index", 0)),
        "content": str(entity.get("content", "")),
        "score": score,
    }


# _deduplicate 按 chunk_id 保留首次出现的候选。
def _deduplicate(items: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    values: Dict[str, Dict[str, Any]] = {}
    for item in items:
        values.setdefault(str(item["chunk_id"]), dict(item))
    return list(values.values())


# _percentile 以 nearest-rank 口径计算耗时分位数。
def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * percentile + 0.999999) - 1))
    return ordered[index]


# _filter_expression 固定离线评测租户、知识库和索引版本。
def _filter_expression(eval_config: Mapping[str, Any]) -> str:
    return (
        f"user_id == {int(eval_config['user_id'])} "
        f"and knowledge_base_id == {int(eval_config['knowledge_base_id'])} "
        f"and index_version == {int(eval_config['index_version'])} "
        "and active == true"
    )


# _build_reranker 按生产配置创建本地或远程 Cross-Encoder 客户端。
def _build_reranker(config: Any) -> Any:
    reranker = config.rag.reranker
    if not reranker.enabled:
        raise ValueError("hybrid_parent_rerank 需要启用 RAG Reranker")
    if reranker.provider == "local":
        return BGEChunkReranker(
            reranker.model_name,
            reranker.batch_size,
            reranker.max_length,
            reranker.use_fp16,
            reranker.device,
        )
    return DashScopeReranker(
        reranker.base_url,
        reranker.api_key,
        reranker.model_name,
        reranker.timeout,
        reranker.batch_size,
    )


# _search_calls 创建共享 Query 向量的 Dense、Sparse 和 RRF 初召回函数。
def _search_calls(
    client: MilvusClient,
    collection: str,
    expression: str,
    vectors: Any,
    initial_top_k: int,
    candidate_limit: int,
    rrf_k: int,
) -> Dict[str, Callable[[int], Sequence[Any]]]:
    output_fields = ["chunk_id", "document_id", "parent_id", "chunk_index", "content"]

    # dense 执行 Dense Child 初召回。
    def dense(index: int) -> Sequence[Any]:
        return client.search(
            collection_name=collection,
            data=[vectors.dense[index]],
            anns_field="dense_vector",
            filter=expression,
            limit=initial_top_k,
            output_fields=output_fields,
        )[0]

    # sparse 执行 Sparse Child 初召回。
    def sparse(index: int) -> Sequence[Any]:
        return client.search(
            collection_name=collection,
            data=[vectors.sparse[index]],
            anns_field="sparse_vector",
            filter=expression,
            limit=initial_top_k,
            output_fields=output_fields,
        )[0]

    # hybrid_rrf 对 Dense/Sparse 候选使用 Milvus RRF 融合。
    def hybrid_rrf(index: int) -> Sequence[Any]:
        requests = [
            AnnSearchRequest(
                [vectors.dense[index]],
                "dense_vector",
                {"metric_type": "COSINE"},
                candidate_limit,
                expr=expression,
            ),
            AnnSearchRequest(
                [vectors.sparse[index]],
                "sparse_vector",
                {"metric_type": "IP"},
                candidate_limit,
                expr=expression,
            ),
        ]
        return client.hybrid_search(
            collection,
            requests,
            RRFRanker(rrf_k),
            limit=initial_top_k,
            output_fields=output_fields,
        )[0]

    return {"dense": dense, "sparse": sparse, "hybrid_rrf": hybrid_rrf}


# _cached_calls 保证 Hybrid 基线和两种 Parent 实验使用相同初召回，并复用原始检索耗时。
def _cached_calls(
    calls: Mapping[str, Callable[[int], Sequence[Any]]],
) -> Dict[str, Callable[[int], tuple[Sequence[Any], float]]]:
    output: Dict[str, Callable[[int], tuple[Sequence[Any], float]]] = {}
    for name, call in calls.items():
        cache: Dict[int, tuple[Sequence[Any], float]] = {}

        # invoke 按 Query 下标只执行一次实际检索。
        def invoke(
            index: int,
            call: Callable[[int], Sequence[Any]] = call,
            cache: Dict[int, tuple[Sequence[Any], float]] = cache,
        ) -> tuple[Sequence[Any], float]:
            if index not in cache:
                started = time.perf_counter()
                rows = call(index)
                cache[index] = (rows, (time.perf_counter() - started) * 1000)
            return cache[index]

        output[name] = invoke
    return output


# _expand_parents 查询初召回命中 Parent 下的全部 Child。
def _expand_parents(
    client: MilvusClient,
    collection: str,
    expression: str,
    initial: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    parent_ids = list(dict.fromkeys(str(item["parent_id"]) for item in initial if item.get("parent_id")))
    if not parent_ids:
        return [dict(item) for item in initial]
    parent_values = ", ".join(json.dumps(value, ensure_ascii=False) for value in parent_ids)
    rows = client.query(
        collection_name=collection,
        filter=f"{expression} and parent_id in [{parent_values}]",
        output_fields=["chunk_id", "document_id", "parent_id", "chunk_index", "content"],
    )
    expanded = [_result_item(row) for row in rows]
    return _deduplicate([*initial, *expanded])


# _rank_parent_expansion 按 Parent 首次激活顺序排列扩展结果，同 Parent 内按原始 Child 顺序排列。
def _rank_parent_expansion(
    initial: Sequence[Mapping[str, Any]],
    expanded: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    candidates = _deduplicate(expanded)
    by_parent: Dict[str, List[Dict[str, Any]]] = {}
    without_parent: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        parent_id = str(item.get("parent_id") or "")
        if parent_id:
            by_parent.setdefault(parent_id, []).append(item)
        else:
            without_parent[str(item["chunk_id"])] = item
    for values in by_parent.values():
        values.sort(key=lambda item: (int(item.get("chunk_index", 0)), str(item["chunk_id"])))

    ranked: List[Dict[str, Any]] = []
    activated = set()
    included_chunks = set()
    for item in initial:
        parent_id = str(item.get("parent_id") or "")
        if parent_id and parent_id not in activated:
            activated.add(parent_id)
            for child in by_parent.get(parent_id, []):
                chunk_id = str(child["chunk_id"])
                if chunk_id not in included_chunks:
                    ranked.append(child)
                    included_chunks.add(chunk_id)
        elif not parent_id:
            chunk_id = str(item["chunk_id"])
            if chunk_id not in included_chunks:
                ranked.append(without_parent.get(chunk_id, dict(item)))
                included_chunks.add(chunk_id)
    for item in candidates:
        chunk_id = str(item["chunk_id"])
        if chunk_id not in included_chunks:
            ranked.append(item)
            included_chunks.add(chunk_id)
    return ranked


# _embed_queries 逐条生成查询向量，使 P50/P95 反映在线单 Query 的 Embedding 延迟。
def _embed_queries(embedder: BGEM3EmbeddingClient, queries: Sequence[Mapping[str, Any]]) -> tuple[EmbeddedChunks, List[float]]:
    dense = []
    sparse = []
    latency_ms = []
    for query in queries:
        started = time.perf_counter()
        vectors = embedder.embed_documents([str(query["evaluation_query"])])
        latency_ms.append((time.perf_counter() - started) * 1000)
        dense.append(vectors.dense[0])
        sparse.append(vectors.sparse[0])
    return EmbeddedChunks(dense=dense, sparse=sparse), latency_ms


# _run_method 执行单种检索方法并保留完整三阶段轨迹。
def _run_method(
    name: str,
    queries: Sequence[Mapping[str, Any]],
    initial_call: Callable[[int], tuple[Sequence[Any], float]],
    embedding_latency_ms: Sequence[float],
    final_top_k: int,
    client: MilvusClient,
    collection: str,
    expression: str,
    reranker: Any | None,
) -> List[Dict[str, Any]]:
    results = []
    for index, query in enumerate(queries):
        initial_rows, hybrid_ms = initial_call(index)
        initial = [_result_item(hit) for hit in initial_rows]
        post_search_started = time.perf_counter()

        expansion_ms = 0.0
        rerank_ms = 0.0
        expanded = list(initial)
        if name in {"hybrid_parent", "hybrid_parent_rerank"}:
            expansion_started = time.perf_counter()
            expanded = _expand_parents(client, collection, expression, initial)
            expansion_ms = (time.perf_counter() - expansion_started) * 1000
        if name == "hybrid_parent_rerank":
            rerank_started = time.perf_counter()
            scores = reranker.score(str(query["evaluation_query"]), [str(item["content"]) for item in expanded])
            ranked = [dict(item, score=float(score)) for item, score in zip(expanded, scores)]
            ranked.sort(key=lambda item: (-float(item["score"]), str(item["chunk_id"])))
            final = ranked[:final_top_k]
            rerank_ms = (time.perf_counter() - rerank_started) * 1000
        elif name == "hybrid_parent":
            final = _rank_parent_expansion(initial, expanded)[:final_top_k]
        else:
            final = list(initial[:final_top_k])

        activated_parent_ids = list(
            dict.fromkeys(str(item["parent_id"]) for item in initial if item.get("parent_id"))
        )
        elapsed_without_shared_embedding = (time.perf_counter() - post_search_started) * 1000
        embedding_ms = float(embedding_latency_ms[index])
        results.append(
            {
                "query_id": query["query_id"],
                "initial": initial,
                "activated_parent_ids": activated_parent_ids,
                "expanded": expanded,
                "final": final,
                "latency_ms": {
                    "embedding": embedding_ms,
                    "hybrid": hybrid_ms,
                    "expansion": expansion_ms,
                    "rerank": rerank_ms,
                    # 缓存命中时墙钟时间不含初召回，仍需使用首次实际检索的耗时。
                    "total": embedding_ms + elapsed_without_shared_embedding + hybrid_ms,
                },
            }
        )
        if (index + 1) % 25 == 0 or index + 1 == len(queries):
            print(f"[{name}] {index + 1}/{len(queries)}", flush=True)
    return results


# _format_metric 将空指标和数值转换成 Markdown 表格文本。
def _format_metric(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        return f"{value:.4f}"
    return str(value)


# _write_report 输出总体指标和 query_type 分组结果。
def _write_report(path: Path, payload: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    final_level = max(int(value) for value in config["final_top_k"])
    keys = (
        f"initial_document_hit@{config['initial_top_k']}",
        f"initial_chunk_recall@{config['initial_top_k']}",
        f"parent_activation_recall@{config['initial_top_k']}",
        f"document_hit@{final_level}",
        f"chunk_recall@{final_level}",
        f"chunk_mrr@{final_level}",
        f"evidence_group_recall@{final_level}",
        f"full_support_hit@{final_level}",
        "context_precision@5",
        f"constraint_violation_rate@{final_level}",
        "latency_total_p95_ms",
    )
    lines = [
        "# Retrieval Evaluation V4",
        "",
        f"- Query 数：{payload['metadata']['query_count']}",
        f"- 数据分区：`{payload['metadata']['dataset_split']}`",
        f"- Query 字段：`{payload['metadata']['query_field']}`",
        f"- 初召回 Top-K：{config['initial_top_k']}",
        f"- 最终 Top-K：{config['final_top_k']}",
        "- Agent / 回答模型：未调用",
        "",
        "## 总体对比",
        "",
        f"| 方法 | Initial Doc Hit | Initial Chunk Recall@{config['initial_top_k']} | Parent Activation | Final Doc Hit@{final_level} | Chunk Recall@{final_level} | Chunk MRR@{final_level} | Evidence Recall@{final_level} | Full Support@{final_level} | Context Precision@5 | Constraint Violation@{final_level} | Total P95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method in payload["methods"]:
        summary = method["metrics"]["summary"]
        lines.append(f"| {method['name']} | " + " | ".join(_format_metric(summary.get(key)) for key in keys) + " |")

    dimension_labels = {
        "query_type": "Query 类型",
        "retrieval_scope": "检索范围",
        "parent_child_count_bucket": "Parent 子块数",
        "difficulty": "难度",
        "query_style": "Query 风格",
    }
    for method in payload["methods"]:
        detail_keys = (
            f"document_hit@{final_level}",
            f"chunk_recall@{final_level}",
            f"parent_activation_recall@{config['initial_top_k']}",
            f"evidence_group_recall@{final_level}",
            f"full_support_hit@{final_level}",
        )
        for dimension, label in dimension_labels.items():
            lines.extend(["", f"## {method['name']} / {label}", ""])
            lines.extend(
                [
                    f"| {label} | Doc Hit@{final_level} | Chunk Recall@{final_level} | Parent Activation@{config['initial_top_k']} | Evidence Recall@{final_level} | Full Support@{final_level} |",
                    "|---|---:|---:|---:|---:|---:|",
                ]
            )
            for value, summary in method["metrics"].get(f"by_{dimension}", {}).items():
                lines.append(
                    f"| {value} | "
                    + " | ".join(_format_metric(summary.get(key)) for key in detail_keys)
                    + " |"
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# _parse_methods 校验命令行检索方法列表。
def _parse_methods(value: str) -> List[str]:
    methods = list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    invalid = sorted(set(methods) - set(CORE_METHODS))
    if not methods or invalid:
        raise ValueError(f"无效检索方法：{invalid or value}")
    return methods


# main 加载 V4 Gold、执行纯检索实验并输出 JSON 与 Markdown 报告。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    parser.add_argument("--eval-config", type=Path, default=Path("tests/evaluation-version4/configs/retrieval_eval.yaml"))
    parser.add_argument("--queries", type=Path, default=Path("tests/evaluation-version4/datasets/queries.jsonl"))
    parser.add_argument("--chunk-gold", type=Path, default=Path("tests/evaluation-version4/datasets/chunk_gold.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("tests/evaluation-version4/reports/retrieval_eval.json"))
    parser.add_argument("--methods", default=",".join(CORE_METHODS))
    parser.add_argument("--query-field", choices=("query", "rewritten_query"), default="query")
    parser.add_argument("--dataset-split", choices=("all", "dev", "test"), default="all")
    parser.add_argument("--initial-top-k", type=int, default=0)
    parser.add_argument("--final-top-k", default="")
    parser.add_argument("--candidate-limit", type=int, default=0)
    parser.add_argument("--require-reviewed", action="store_true")
    parser.add_argument("--query-offset", type=int, default=0)
    parser.add_argument("--max-queries", type=int, default=0)
    args = parser.parse_args()
    if args.query_offset < 0 or args.max_queries < 0 or args.initial_top_k < 0 or args.candidate_limit < 0:
        raise ValueError("query_offset、max_queries 和 Top-K 覆盖参数不能为负数")

    methods = _parse_methods(args.methods)
    eval_config = yaml.safe_load(args.eval_config.read_text(encoding="utf-8"))
    app_config = load_config(str(args.config))
    queries = _load_jsonl(args.queries)
    if args.dataset_split != "all":
        queries = [query for query in queries if query.get("dataset_split") == args.dataset_split]
    if args.require_reviewed:
        unreviewed = [query["query_id"] for query in queries if query.get("label_status") != "reviewed"]
        if unreviewed:
            raise ValueError(f"存在 {len(unreviewed)} 条未人工审核 Query，不能运行正式基准")
    if args.query_offset:
        queries = queries[args.query_offset :]
    if args.max_queries:
        queries = queries[: args.max_queries]
    if not queries:
        raise ValueError("没有可评估的 Query")
    _attach_chunk_gold(queries, _load_jsonl(args.chunk_gold))
    if args.require_reviewed:
        unreviewed_gold = [
            query["query_id"]
            for query in queries
            if query.get("chunk_gold") and query["chunk_gold"].get("label_status") != "reviewed"
        ]
        if unreviewed_gold:
            raise ValueError(f"存在 {len(unreviewed_gold)} 条未人工审核 Chunk Gold，不能运行正式基准")
    for query in queries:
        value = query.get(args.query_field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Query 缺少字段 {args.query_field}: {query['query_id']}")
        query["evaluation_query"] = value

    initial_top_k = args.initial_top_k or int(eval_config["initial_top_k"])
    final_levels = (
        [int(value.strip()) for value in args.final_top_k.split(",") if value.strip()]
        if args.final_top_k
        else [int(value) for value in eval_config["final_top_k"]]
    )
    if initial_top_k <= 0 or not final_levels or any(value <= 0 for value in final_levels):
        raise ValueError("initial_top_k 和 final_top_k 必须为正数")
    final_top_k = max(final_levels)
    candidate_limit = max(args.candidate_limit or int(eval_config["candidate_limit"]), initial_top_k)
    collection = str(eval_config.get("collection") or app_config.rag.milvus.collection)
    expression = _filter_expression(eval_config)

    embedder = BGEM3EmbeddingClient(
        app_config.rag.embedding.model_name,
        app_config.rag.embedding.batch_size,
        app_config.rag.embedding.use_fp16,
        app_config.rag.embedding.device,
    )
    vectors, embedding_latency_ms = _embed_queries(embedder, queries)
    embedding_total_ms = sum(embedding_latency_ms)
    embedder.close()
    embedding_ms_per_query = embedding_total_ms / len(queries)

    client = MilvusClient(
        uri=app_config.rag.milvus.uri,
        db_name=app_config.rag.milvus.database,
        token=app_config.rag.milvus.token or None,
        timeout=120,
    )
    calls = _cached_calls(
        _search_calls(
            client,
            collection,
            expression,
            vectors,
            initial_top_k,
            candidate_limit,
            int(eval_config["rrf_k"]),
        )
    )
    reranker = _build_reranker(app_config) if "hybrid_parent_rerank" in methods else None
    method_payloads = []
    try:
        for method in methods:
            base_method = "hybrid_rrf" if method in {"hybrid_parent", "hybrid_parent_rerank"} else method
            results = _run_method(
                method,
                queries,
                calls[base_method],
                embedding_latency_ms,
                final_top_k,
                client,
                collection,
                expression,
                reranker,
            )
            metrics = evaluate_retrieval(
                queries,
                results,
                initial_top_k,
                final_levels,
                eval_config.get("no_answer_threshold"),
            )
            method_payloads.append({"name": method, "metrics": metrics, "results": results})
    finally:
        if reranker is not None:
            reranker.close()
        client.close()

    for query in queries:
        query.pop("evaluation_query", None)
    payload = {
        "metadata": {
            "query_count": len(queries),
            "dataset_split": args.dataset_split,
            "query_field": args.query_field,
            "collection": collection,
            "embedding_total_ms": embedding_total_ms,
            "embedding_mean_ms": embedding_ms_per_query,
            "agent_or_answer_model_called": False,
        },
        "methods": method_payloads,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_report(args.output.with_suffix(".md"), payload, {"initial_top_k": initial_top_k, "final_top_k": final_levels})
    print(args.output)
    print(args.output.with_suffix(".md"))


if __name__ == "__main__":
    main()
