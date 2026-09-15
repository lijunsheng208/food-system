"""验证 V4 执行器的 Parent 扩展排序与检索耗时复用。"""

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = PROJECT_ROOT / "tests/evaluation-version4/scripts/run_evaluation.py"


# _load_runner 从带连字符的评测目录加载执行器模块。
def _load_runner():
    spec = importlib.util.spec_from_file_location("evaluation_v4_run", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# _item 构造包含 Parent 和原始 Child 顺序的最小候选。
def _item(chunk_id, parent_id, chunk_index, score=None):
    return {
        "chunk_id": chunk_id,
        "parent_id": parent_id,
        "document_id": 1,
        "chunk_index": chunk_index,
        "content": chunk_id,
        "score": score,
    }


# test_parent_expansion_follows_parent_activation_order 验证兄弟 Child 紧随首次激活的 Parent。
def test_parent_expansion_follows_parent_activation_order():
    runner = _load_runner()
    initial = [_item("p2-c1", "p2", 3, 0.9), _item("p1-c1", "p1", 1, 0.8)]
    expanded = [
        *initial,
        _item("p1-c0", "p1", 0),
        _item("p2-c0", "p2", 2),
    ]

    ranked = runner._rank_parent_expansion(initial, expanded)

    assert [item["chunk_id"] for item in ranked] == ["p2-c0", "p2-c1", "p1-c0", "p1-c1"]


# test_cached_calls_preserve_original_latency 验证共享初召回不会把后续方法耗时错误记为零。
def test_cached_calls_preserve_original_latency():
    runner = _load_runner()
    invocation_count = 0

    def search(_index):
        nonlocal invocation_count
        invocation_count += 1
        return ["hit"]

    call = runner._cached_calls({"hybrid": search})["hybrid"]
    first_rows, first_ms = call(0)
    second_rows, second_ms = call(0)

    assert invocation_count == 1
    assert first_rows == second_rows == ["hit"]
    assert first_ms == second_ms
    assert first_ms >= 0


# test_attach_chunk_gold_supports_query_subset 验证运行测试集切片时可关联全量 qrels。
def test_attach_chunk_gold_supports_query_subset():
    runner = _load_runner()
    queries = [
        {"query_id": "q-evidence", "evidence_groups": [{"group_id": "eg-1"}]},
        {"query_id": "q-document", "evidence_groups": []},
    ]
    chunk_gold = [
        {"query_id": "q-evidence", "judgments": [{"chunk_id": "c-1", "relevance": 3}]},
        {"query_id": "q-not-selected", "judgments": [{"chunk_id": "c-2", "relevance": 3}]},
    ]

    runner._attach_chunk_gold(queries, chunk_gold)

    assert queries[0]["chunk_gold"]["judgments"][0]["chunk_id"] == "c-1"
    assert "chunk_gold" not in queries[1]


# test_attach_chunk_gold_allows_document_only_subset 验证文档型切片无需伪造 Chunk Gold。
def test_attach_chunk_gold_allows_document_only_subset():
    runner = _load_runner()
    queries = [{"query_id": "q-document", "evidence_groups": []}]
    chunk_gold = [
        {"query_id": "q-not-selected", "judgments": [{"chunk_id": "c-2", "relevance": 3}]},
    ]

    runner._attach_chunk_gold(queries, chunk_gold)

    assert "chunk_gold" not in queries[0]
