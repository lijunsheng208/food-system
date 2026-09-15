"""计算文档、Parent、证据组和最终上下文的分层检索指标。"""

import math
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


# _mean 对空序列返回 None，避免把没有适用样本的指标误报为 0。
def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


# _percentile 使用 nearest-rank 口径计算延迟分位数。
def _percentile(values: Sequence[float], percentile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index]


# _items 从一次查询结果中读取指定阶段的候选列表。
def _items(result: Mapping[str, Any], stage: str, limit: Optional[int] = None) -> List[Mapping[str, Any]]:
    values = list(result.get(stage) or [])
    return values if limit is None else values[:limit]


# _unique_document_ids 按首次出现顺序生成去重后的文档排名。
def _unique_document_ids(items: Sequence[Mapping[str, Any]]) -> List[int]:
    values: List[int] = []
    seen = set()
    for item in items:
        document_id = int(item["document_id"])
        if document_id not in seen:
            values.append(document_id)
            seen.add(document_id)
    return values


# _unique_chunk_ids 按首次出现顺序生成去重后的 Child Chunk 排名。
def _unique_chunk_ids(items: Sequence[Mapping[str, Any]]) -> List[str]:
    values: List[str] = []
    seen = set()
    for item in items:
        chunk_id = str(item["chunk_id"])
        if chunk_id not in seen:
            values.append(chunk_id)
            seen.add(chunk_id)
    return values


# _document_relevance 读取文档分级标签，并兼容仅包含 document_id 的记录。
def _document_relevance(query: Mapping[str, Any]) -> Dict[int, int]:
    values: Dict[int, int] = {}
    for item in query.get("relevant_documents") or []:
        if isinstance(item, Mapping):
            values[int(item["document_id"])] = int(item.get("relevance", 1))
        else:
            values[int(item)] = 1
    return values


# _chunk_relevance 读取独立 Chunk Gold 中经过逐 ID 标注的分级相关性。
def _chunk_relevance(query: Mapping[str, Any]) -> Dict[str, int]:
    gold = query.get("chunk_gold") or {}
    return {
        str(judgment["chunk_id"]): int(judgment.get("relevance", 1))
        for judgment in gold.get("judgments") or []
    }


# _required_groups 返回参与完整证据判定的必需证据组。
def _required_groups(query: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [group for group in query.get("evidence_groups") or [] if group.get("required", True)]


# _group_recall 计算候选 Child 对必需证据组的覆盖比例。
def _group_recall(groups: Sequence[Mapping[str, Any]], chunk_ids: set[str]) -> float:
    if not groups:
        return 0.0
    hits = sum(bool(set(group.get("acceptable_child_ids") or []) & chunk_ids) for group in groups)
    return hits / len(groups)


# _parent_activation_recall 按唯一 Parent 需求计算激活率，同 Parent 的多个事实只计一次。
def _parent_activation_recall(groups: Sequence[Mapping[str, Any]], parent_ids: set[str]) -> float:
    parent_requirements = {
        frozenset(str(parent_id) for parent_id in group.get("acceptable_parent_ids") or [])
        for group in groups
        if group.get("acceptable_parent_ids")
    }
    if not parent_requirements:
        return 0.0
    return sum(bool(requirement & parent_ids) for requirement in parent_requirements) / len(parent_requirements)


# _document_metrics 计算单目标命中、多目标召回、MRR 和分级 NDCG。
def _document_metrics(
    queries: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    stage: str,
    level: int,
) -> Dict[str, Optional[float]]:
    hits: List[float] = []
    recalls: List[float] = []
    reciprocal_ranks: List[float] = []
    ndcgs: List[float] = []
    for query, result in zip(queries, results):
        relevance = _document_relevance(query)
        if not relevance:
            continue
        ranked = _unique_document_ids(_items(result, stage, level))
        relevant_ids = set(relevance)
        found = relevant_ids & set(ranked)
        hits.append(float(bool(found)))
        recalls.append(len(found) / len(relevant_ids))
        first_rank = next((index + 1 for index, value in enumerate(ranked) if value in relevant_ids), None)
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)

        dcg = sum(
            (2 ** relevance.get(document_id, 0) - 1) / math.log2(index + 2)
            for index, document_id in enumerate(ranked)
        )
        ideal_grades = sorted(relevance.values(), reverse=True)[:level]
        ideal = sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(ideal_grades))
        ndcgs.append(dcg / ideal if ideal else 0.0)
    return {
        f"document_hit@{level}": _mean(hits),
        f"document_recall@{level}": _mean(recalls),
        f"document_mrr@{level}": _mean(reciprocal_ranks),
        f"document_ndcg@{level}": _mean(ndcgs),
    }


# _chunk_metrics 计算严格 Child ID 口径的 Hit、Recall、Precision、MRR 和分级 NDCG。
def _chunk_metrics(
    queries: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    stage: str,
    level: int,
    prefix: str = "",
) -> Dict[str, Optional[float]]:
    hits: List[float] = []
    recalls: List[float] = []
    precisions: List[float] = []
    reciprocal_ranks: List[float] = []
    ndcgs: List[float] = []
    for query, result in zip(queries, results):
        relevance = _chunk_relevance(query)
        if not relevance:
            continue
        ranked = _unique_chunk_ids(_items(result, stage, level))
        relevant_ids = set(relevance)
        found = relevant_ids & set(ranked)
        hits.append(float(bool(found)))
        recalls.append(len(found) / len(relevant_ids))
        precisions.append(len(found) / level)
        first_rank = next((index + 1 for index, value in enumerate(ranked) if value in relevant_ids), None)
        reciprocal_ranks.append(1.0 / first_rank if first_rank else 0.0)

        dcg = sum(
            (2 ** relevance.get(chunk_id, 0) - 1) / math.log2(index + 2)
            for index, chunk_id in enumerate(ranked)
        )
        ideal_grades = sorted(relevance.values(), reverse=True)[:level]
        ideal = sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(ideal_grades))
        ndcgs.append(dcg / ideal if ideal else 0.0)
    return {
        f"{prefix}chunk_hit@{level}": _mean(hits),
        f"{prefix}chunk_recall@{level}": _mean(recalls),
        f"{prefix}chunk_precision@{level}": _mean(precisions),
        f"{prefix}chunk_mrr@{level}": _mean(reciprocal_ranks),
        f"{prefix}chunk_ndcg@{level}": _mean(ndcgs),
    }


# _evidence_metrics 计算最终 Top-K 对证据组的任意命中、完整覆盖和上下文精度。
def _evidence_metrics(
    queries: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    stage: str,
    level: int,
) -> Dict[str, Optional[float]]:
    any_hits: List[float] = []
    group_recalls: List[float] = []
    full_support_hits: List[float] = []
    context_precisions: List[float] = []
    for query, result in zip(queries, results):
        groups = _required_groups(query)
        if not groups:
            continue
        items = _items(result, stage, level)
        chunk_ids = {str(item["chunk_id"]) for item in items}
        group_recall = _group_recall(groups, chunk_ids)
        relevant_child_ids = {
            str(chunk_id)
            for group in groups
            for chunk_id in group.get("acceptable_child_ids") or []
        }
        any_hits.append(float(group_recall > 0))
        group_recalls.append(group_recall)
        full_support_hits.append(float(math.isclose(group_recall, 1.0)))
        context_precisions.append(
            sum(str(item["chunk_id"]) in relevant_child_ids for item in items) / len(items)
            if items else 0.0
        )
    return {
        f"any_evidence_hit@{level}": _mean(any_hits),
        f"evidence_group_recall@{level}": _mean(group_recalls),
        f"full_support_hit@{level}": _mean(full_support_hits),
        f"context_precision@{level}": _mean(context_precisions),
    }


# _pipeline_metrics 定位证据在初召回、Parent 扩展和最终重排阶段的变化。
def _pipeline_metrics(
    queries: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    initial_level: int,
) -> Dict[str, Optional[float]]:
    parent_recalls: List[float] = []
    initial_group_recalls: List[float] = []
    expanded_group_recalls: List[float] = []
    expansion_gains: List[float] = []
    initial_counts: List[float] = []
    expanded_counts: List[float] = []
    initial_document_hits: List[float] = []
    initial_any_evidence_hits: List[float] = []
    for query, result in zip(queries, results):
        initial_items = _items(result, "initial", initial_level)
        expanded_items = _items(result, "expanded")
        initial_counts.append(float(len(initial_items)))
        expanded_counts.append(float(len(expanded_items)))
        relevant_documents = set(_document_relevance(query))
        if relevant_documents:
            initial_documents = set(_unique_document_ids(initial_items))
            initial_document_hits.append(float(bool(relevant_documents & initial_documents)))
        groups = _required_groups(query)
        if not groups:
            continue
        initial_chunks = {str(item["chunk_id"]) for item in initial_items}
        initial_parents = {str(item["parent_id"]) for item in initial_items if item.get("parent_id")}
        expanded_chunks = {str(item["chunk_id"]) for item in expanded_items}
        initial_recall = _group_recall(groups, initial_chunks)
        expanded_recall = _group_recall(groups, expanded_chunks)
        initial_any_evidence_hits.append(float(initial_recall > 0))
        parent_recalls.append(_parent_activation_recall(groups, initial_parents))
        initial_group_recalls.append(initial_recall)
        expanded_group_recalls.append(expanded_recall)
        expansion_gains.append(expanded_recall - initial_recall)
    return {
        f"initial_document_hit@{initial_level}": _mean(initial_document_hits),
        f"initial_any_evidence_hit@{initial_level}": _mean(initial_any_evidence_hits),
        f"parent_activation_recall@{initial_level}": _mean(parent_recalls),
        f"initial_evidence_group_recall@{initial_level}": _mean(initial_group_recalls),
        "expanded_evidence_group_recall": _mean(expanded_group_recalls),
        "expansion_gain": _mean(expansion_gains),
        "initial_candidate_count_mean": _mean(initial_counts),
        "expanded_candidate_count_mean": _mean(expanded_counts),
    }


# _constraint_metrics 将未进入完整合格文档集合的结果计为约束违反。
def _constraint_metrics(
    queries: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    stage: str,
    level: int,
) -> Dict[str, Optional[float]]:
    violation_rates: List[float] = []
    zero_violation_hits: List[float] = []
    for query, result in zip(queries, results):
        if query.get("query_type") != "constraint":
            continue
        eligible = set(_document_relevance(query))
        ranked = _unique_document_ids(_items(result, stage, level))
        if not ranked:
            violation_rates.append(0.0)
            zero_violation_hits.append(1.0)
            continue
        violation_rate = sum(document_id not in eligible for document_id in ranked) / len(ranked)
        violation_rates.append(violation_rate)
        zero_violation_hits.append(float(math.isclose(violation_rate, 0.0)))
    return {
        f"constraint_violation_rate@{level}": _mean(violation_rates),
        f"constraint_zero_violation_hit@{level}": _mean(zero_violation_hits),
    }


# _no_answer_metrics 通过最终重排最高分评估无答案查询的阈值误触发率。
def _no_answer_metrics(
    queries: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    threshold: Optional[float],
) -> Dict[str, Optional[float]]:
    top_scores: List[float] = []
    mean_scores: List[float] = []
    false_positives: List[float] = []
    for query, result in zip(queries, results):
        if query.get("answerable", True):
            continue
        final_items = _items(result, "final")
        scores = [float(item["score"]) for item in final_items if item.get("score") is not None]
        score = max(scores, default=None)
        if score is not None:
            top_scores.append(score)
            mean_scores.append(sum(scores) / len(scores))
            if threshold is not None:
                false_positives.append(float(score >= threshold))
    output: Dict[str, Optional[float]] = {
        "no_answer_query_count": float(sum(not query.get("answerable", True) for query in queries)),
        "no_answer_top1_score_mean": _mean(top_scores),
        "no_answer_top1_score_p95": _percentile(top_scores, 0.95),
        "no_answer_topk_score_mean": _mean(mean_scores),
    }
    if threshold is not None:
        output[f"no_answer_false_positive_rate@{threshold:g}"] = _mean(false_positives)
    return output


# classify_failure 根据三阶段结果为可回答 Query 生成首要失败原因。
def classify_failure(
    query: Mapping[str, Any],
    result: Mapping[str, Any],
    initial_level: int,
    final_level: int,
) -> Optional[str]:
    if not query.get("answerable", True):
        return None
    relevant_documents = set(_document_relevance(query))
    initial_items = _items(result, "initial", initial_level)
    initial_documents = set(_unique_document_ids(initial_items))
    if relevant_documents and not (relevant_documents & initial_documents):
        return "DOCUMENT_MISS"

    groups = _required_groups(query)
    if not groups:
        final_documents = set(_unique_document_ids(_items(result, "final", final_level)))
        return None if relevant_documents & final_documents else "RERANK_DROP"

    initial_parents = {str(item["parent_id"]) for item in initial_items if item.get("parent_id")}
    if not math.isclose(_parent_activation_recall(groups, initial_parents), 1.0):
        return "PARENT_MISS"

    final_chunks = {str(item["chunk_id"]) for item in _items(result, "final", final_level)}
    final_recall = _group_recall(groups, final_chunks)
    if math.isclose(final_recall, 1.0):
        return None
    if final_recall > 0:
        return "PARTIAL_EVIDENCE"

    expanded_chunks = {str(item["chunk_id"]) for item in _items(result, "expanded")}
    if _group_recall(groups, expanded_chunks) > 0:
        return "RERANK_DROP"
    if relevant_documents & initial_documents:
        return "POSSIBLE_LABEL_GAP"
    return "DOCUMENT_MISS"


# _latency_metrics 汇总检索各阶段和端到端耗时。
def _latency_metrics(results: Sequence[Mapping[str, Any]]) -> Dict[str, Optional[float]]:
    output: Dict[str, Optional[float]] = {}
    values_by_stage: Dict[str, List[float]] = defaultdict(list)
    for result in results:
        for stage, value in (result.get("latency_ms") or {}).items():
            values_by_stage[str(stage)].append(float(value))
    for stage, values in values_by_stage.items():
        output[f"latency_{stage}_p50_ms"] = statistics.median(values) if values else None
        output[f"latency_{stage}_p95_ms"] = _percentile(values, 0.95)
    return output


# evaluate_retrieval 汇总检索全链路指标，并按 query_type 生成同口径切片。
def evaluate_retrieval(
    queries: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    initial_level: int,
    final_levels: Sequence[int],
    no_answer_threshold: Optional[float] = None,
    include_breakdown: bool = True,
) -> Dict[str, Any]:
    if len(queries) != len(results):
        raise ValueError("Query 与检索结果数量不一致")
    if initial_level <= 0 or not final_levels or any(level <= 0 for level in final_levels):
        raise ValueError("评测 Top-K 必须为正数")

    summary: Dict[str, Any] = {
        "query_count": len(queries),
        "answerable_query_count": sum(query.get("answerable", True) for query in queries),
        "evidence_query_count": sum(bool(_required_groups(query)) for query in queries),
        "chunk_gold_query_count": sum(bool(_chunk_relevance(query)) for query in queries),
    }
    summary.update(_pipeline_metrics(queries, results, initial_level))
    summary.update(_chunk_metrics(queries, results, "initial", initial_level, prefix="initial_"))
    for level in sorted(set(final_levels)):
        summary.update(_document_metrics(queries, results, "final", level))
        summary.update(_chunk_metrics(queries, results, "final", level))
        summary.update(_evidence_metrics(queries, results, "final", level))
        summary.update(_constraint_metrics(queries, results, "final", level))
    summary.update(_no_answer_metrics(queries, results, no_answer_threshold))
    summary.update(_latency_metrics(results))

    failure_level = max(final_levels)
    failures = []
    for query, result in zip(queries, results):
        reason = classify_failure(query, result, initial_level, failure_level)
        if reason:
            failures.append({"query_id": query["query_id"], "reason": reason})
    summary["failure_counts"] = dict(
        sorted(
            ((reason, sum(item["reason"] == reason for item in failures)) for reason in {item["reason"] for item in failures}),
            key=lambda item: item[0],
        )
    )

    output: Dict[str, Any] = {"summary": summary, "failures": failures}
    if include_breakdown:
        dimensions = (
            "query_type",
            "retrieval_scope",
            "parent_child_count_bucket",
            "difficulty",
            "query_style",
        )
        for dimension in dimensions:
            breakdown = {}
            values = sorted({str(query.get(dimension, "unknown")) for query in queries})
            for value in values:
                indexes = [
                    index
                    for index, query in enumerate(queries)
                    if str(query.get(dimension, "unknown")) == value
                ]
                subset = evaluate_retrieval(
                    [queries[index] for index in indexes],
                    [results[index] for index in indexes],
                    initial_level,
                    final_levels,
                    no_answer_threshold,
                    include_breakdown=False,
                )
                breakdown[value] = subset["summary"]
            output[f"by_{dimension}"] = breakdown
    return output
