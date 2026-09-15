"""验证 V4 Parent 激活、证据覆盖和失败归因指标。"""

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
METRICS_PATH = PROJECT_ROOT / "tests/evaluation-version4/lib/metrics.py"


# _load_metrics 从带连字符的评测目录加载指标模块。
def _load_metrics():
    spec = importlib.util.spec_from_file_location("evaluation_v4_metrics", METRICS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# _query 构造需要两个不同 Parent 的最小 Gold Query。
def _query():
    return {
        "query_id": "q-1",
        "query_type": "cross_parent",
        "answerable": True,
        "relevant_documents": [{"document_id": 1, "relevance": 3}],
        "evidence_groups": [
            {
                "required": True,
                "acceptable_parent_ids": ["p-ingredients"],
                "acceptable_child_ids": ["c-ingredients", "c-ingredients-overlap"],
            },
            {
                "required": True,
                "acceptable_parent_ids": ["p-operation"],
                "acceptable_child_ids": ["c-operation"],
            },
        ],
    }


# _item 构造指标计算所需的最小检索命中。
def _item(chunk_id, parent_id, document_id=1, score=0.8):
    return {
        "chunk_id": chunk_id,
        "parent_id": parent_id,
        "document_id": document_id,
        "content": chunk_id,
        "score": score,
    }


# test_partial_parent_activation_is_not_full_support 验证任意证据命中不会冒充完整召回。
def test_partial_parent_activation_is_not_full_support():
    metrics = _load_metrics()
    result = {
        "initial": [_item("c-ingredients", "p-ingredients")],
        "expanded": [_item("c-ingredients", "p-ingredients")],
        "final": [_item("c-ingredients", "p-ingredients")],
        "latency_ms": {"total": 10},
    }

    output = metrics.evaluate_retrieval([_query()], [result], 50, [5, 10])
    summary = output["summary"]

    assert summary["initial_any_evidence_hit@50"] == 1.0
    assert summary["parent_activation_recall@50"] == 0.5
    assert summary["evidence_group_recall@10"] == 0.5
    assert summary["full_support_hit@10"] == 0.0
    assert summary["failure_counts"] == {"PARENT_MISS": 1}


# test_rerank_drop_is_attributed_after_full_parent_activation 验证扩展命中但重排丢失的归因。
def test_rerank_drop_is_attributed_after_full_parent_activation():
    metrics = _load_metrics()
    initial = [
        _item("other-1", "p-ingredients"),
        _item("other-2", "p-operation"),
    ]
    expanded = [
        *initial,
        _item("c-ingredients", "p-ingredients"),
        _item("c-operation", "p-operation"),
    ]
    result = {
        "initial": initial,
        "expanded": expanded,
        "final": [_item("other-1", "p-ingredients")],
        "latency_ms": {"total": 10},
    }

    output = metrics.evaluate_retrieval([_query()], [result], 50, [10])

    assert output["summary"]["expanded_evidence_group_recall"] == 1.0
    assert output["summary"]["full_support_hit@10"] == 0.0
    assert output["summary"]["failure_counts"] == {"RERANK_DROP": 1}


# test_parent_activation_deduplicates_groups_in_same_parent 验证同 Parent 的多个事实不重复扩大分母。
def test_parent_activation_deduplicates_groups_in_same_parent():
    metrics = _load_metrics()
    groups = [
        {"acceptable_parent_ids": ["p-calculation"], "acceptable_child_ids": ["c-egg"]},
        {"acceptable_parent_ids": ["p-calculation"], "acceptable_child_ids": ["c-salt"]},
        {"acceptable_parent_ids": ["p-operation"], "acceptable_child_ids": ["c-operation"]},
    ]

    recall = metrics._parent_activation_recall(groups, {"p-calculation"})

    assert recall == 0.5


# test_strict_chunk_recall_counts_overlap_ids_individually 验证严格 Chunk 指标不折叠 overlap 等价块。
def test_strict_chunk_recall_counts_overlap_ids_individually():
    metrics = _load_metrics()
    query = _query()
    query["chunk_gold"] = {
        "judgments": [
            {"chunk_id": "c-ingredients", "relevance": 3},
            {"chunk_id": "c-ingredients-overlap", "relevance": 3},
            {"chunk_id": "c-operation", "relevance": 3},
        ]
    }
    result = {
        "initial": [_item("c-ingredients", "p-ingredients")],
        "expanded": [_item("c-ingredients", "p-ingredients")],
        "final": [_item("c-ingredients", "p-ingredients")],
        "latency_ms": {"total": 10},
    }

    summary = metrics.evaluate_retrieval([query], [result], 50, [5])["summary"]

    assert summary["chunk_gold_query_count"] == 1
    assert summary["initial_chunk_recall@50"] == 1 / 3
    assert summary["chunk_hit@5"] == 1.0
    assert summary["chunk_recall@5"] == 1 / 3
    assert summary["chunk_precision@5"] == 0.2
    assert summary["chunk_mrr@5"] == 1.0
    assert summary["evidence_group_recall@5"] == 0.5


# test_document_only_query_is_excluded_from_chunk_metrics 验证无 Chunk Gold 的文档型 Query 不污染均值。
def test_document_only_query_is_excluded_from_chunk_metrics():
    metrics = _load_metrics()
    query = {
        "query_id": "q-document",
        "query_type": "dish_lookup",
        "answerable": True,
        "relevant_documents": [{"document_id": 1, "relevance": 3}],
        "evidence_groups": [],
    }
    result = {
        "initial": [_item("c-overview", "p-overview")],
        "expanded": [_item("c-overview", "p-overview")],
        "final": [_item("c-overview", "p-overview")],
        "latency_ms": {"total": 10},
    }

    summary = metrics.evaluate_retrieval([query], [result], 50, [5])["summary"]

    assert summary["chunk_gold_query_count"] == 0
    assert summary["chunk_recall@5"] is None
