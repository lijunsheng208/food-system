"""验证 V4 Query 数据集的固定配额和 Gold 层级契约。"""

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
GENERATOR_PATH = PROJECT_ROOT / "tests/evaluation-version4/scripts/generate_queries.py"
MAPPING_PATH = PROJECT_ROOT / "tests/evaluation-version1/datasets/raw/chunks.jsonl"


# _load_generator 从带连字符的评测目录加载生成模块。
def _load_generator():
    spec = importlib.util.spec_from_file_location("evaluation_v4_generate_queries", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# test_generated_dataset_has_exact_quotas 验证 300 条 Query 的类型配额完全一致。
def test_generated_dataset_has_exact_quotas():
    generator = _load_generator()
    profiles = generator._load_profiles(MAPPING_PATH)
    records = generator.build_records(profiles)

    summary = generator.validate_records(records, profiles)

    assert summary["query_count"] == 300
    assert summary["query_type_counts"] == generator.QUOTAS
    assert summary["label_status_counts"] == {"needs_review": 300}
    assert summary["query_style_counts"]["typo"] == 7
    assert all(len({record["dataset_split"] for record in records if record["intent_id"] == intent_id}) == 1 for intent_id in {record["intent_id"] for record in records})
    assert all(
        len({record["dataset_split"] for record in records if record.get("primary_source") == source}) == 1
        for source in {record.get("primary_source") for record in records if record.get("primary_source")}
    )


# test_generated_chunk_gold_strictly_covers_evidence_children 验证独立 qrels 平铺全部证据 Child。
def test_generated_chunk_gold_strictly_covers_evidence_children():
    generator = _load_generator()
    profiles = generator._load_profiles(MAPPING_PATH)
    records = generator.build_records(profiles)
    chunk_gold = generator.build_chunk_gold(records, profiles)

    summary = generator.validate_chunk_gold(chunk_gold, records, profiles)

    assert summary["chunk_gold_query_count"] == 195
    assert summary["chunk_gold_judgment_count"] >= 195
    assert summary["chunk_gold_label_status_counts"] == {"needs_review": 195}
    records_by_id = {record["query_id"]: record for record in records}
    for item in chunk_gold:
        expected = list(
            dict.fromkeys(
                child_id
                for group in records_by_id[item["query_id"]]["evidence_groups"]
                if group.get("required", True)
                for child_id in group["acceptable_child_ids"]
            )
        )
        assert item["relevant_child_ids"] == expected
        assert [judgment["chunk_id"] for judgment in item["judgments"]] == expected


# test_cross_parent_queries_require_distinct_parents 验证跨章节 Query 确实需要多个 Parent。
def test_cross_parent_queries_require_distinct_parents():
    generator = _load_generator()
    profiles = generator._load_profiles(MAPPING_PATH)
    records = generator.build_records(profiles)
    cross_parent = [record for record in records if record["query_type"] == "cross_parent"]

    assert len(cross_parent) == 60
    assert all(len(record["evidence_groups"]) >= 2 for record in cross_parent)
    assert all(
        len(
            {
                parent_id
                for group in record["evidence_groups"]
                for parent_id in group["acceptable_parent_ids"]
            }
        )
        >= 2
        for record in cross_parent
    )


# test_unanswerable_queries_have_no_positive_labels 验证无答案 Query 不携带伪造正例。
def test_unanswerable_queries_have_no_positive_labels():
    generator = _load_generator()
    profiles = generator._load_profiles(MAPPING_PATH)
    records = generator.build_records(profiles)
    unanswerable = [record for record in records if record["query_type"] == "unanswerable"]

    assert len(unanswerable) == 10
    assert all(record["answerable"] is False for record in unanswerable)
    assert all(not record["relevant_documents"] and not record["evidence_groups"] for record in unanswerable)
