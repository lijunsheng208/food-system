"""生成不包含 Numeric/Negative 约束类型的通用检索评测集。"""

import argparse
import json
from collections import Counter
from pathlib import Path

import generate_queries as legacy


QUERY_TYPES = ("dish_name", "ingredient", "taste_scene", "semantic_description")


# _select_profiles 按类别选择文本证据较完整的菜谱，避免用数值字段决定通用检索样本。
def _select_profiles(profiles, sources_per_category):
    selected = []
    for category in legacy.CATEGORY_ORDER:
        candidates = [profile for profile in profiles if profile["category"] == category]
        candidates.sort(
            key=lambda item: (
                not bool(item["ingredients"]),
                not bool(item["operations"]),
                not bool(item["overview"]),
                -len(item["text"]),
                item["source"],
            )
        )
        selected.extend(candidates[:sources_per_category])
    expected = sources_per_category * len(legacy.CATEGORY_ORDER)
    if len(selected) != expected:
        raise ValueError(f"菜谱类别覆盖不足：expected={expected}, actual={len(selected)}")
    return selected


# _build_records 为每篇菜谱生成四类以局部文本为证据的通用检索 Query。
def _build_records(profiles, sources_per_category):
    selected = _select_profiles(profiles, sources_per_category)
    records = []
    for profile in selected:
        anchors = legacy.choose_anchors(profile)
        anchor_text = "、".join(anchors)
        definitions = (
            (
                f"请给出{profile['title']}的完整用料和关键步骤。",
                "dish_name",
                [legacy.ingredient_chunk(profile, anchors[0]), legacy.operation_chunk(profile, anchors[0])],
            ),
            (
                f"家里有{anchor_text}，想做一道{legacy.CATEGORY_LABELS[profile['category']]}，应该怎样准备和烹饪？",
                "ingredient",
                [legacy.ingredient_chunk(profile, anchors[0]), legacy.operation_chunk(profile, anchors[0])],
            ),
            (
                f"想吃{legacy.taste_phrase(profile)}、以{anchors[0]}为主的{legacy.CATEGORY_LABELS[profile['category']]}，有什么具体做法？",
                "taste_scene",
                [legacy.overview_chunk(profile), legacy.operation_chunk(profile, anchors[0])],
            ),
            (
                legacy.semantic_query(profile, anchors),
                "semantic_description",
                [legacy.operation_chunk(profile), legacy.overview_chunk(profile)],
            ),
        )
        for query, query_type, chunks in definitions:
            record = legacy.query_record(
                profile,
                query,
                query_type,
                chunks,
                legacy.choose_hard_negatives(profile, profiles, query_type, anchor=anchors[0]),
                dataset_version="v2",
                retrieval_intent="general_retrieval",
            )
            records.append(record)
    return records, selected


# _validate_records 校验 V2 类型、数量以及正例 Chunk 的文档归属。
def _validate_records(records, selected):
    counts = Counter(record["query_type"] for record in records)
    expected_count = len(selected)
    if set(counts) != set(QUERY_TYPES) or any(counts[value] != expected_count for value in QUERY_TYPES):
        raise ValueError(f"Query 类型或数量不正确：{dict(counts)}")
    chunk_documents = {
        row["chunk_id"]: row["document_id"]
        for profile in selected
        for row in profile["rows"]
    }
    for record in records:
        if record["forbidden_terms"] or record["numeric_constraints"] or record["constraint_type"] is not None:
            raise ValueError(f"通用检索 Query 不应包含约束：{record['query_id']}")
        expected_document = record["positive_documents"][0]
        if not record["positive_chunks"]:
            raise ValueError(f"Query 缺少正例 Chunk：{record['query_id']}")
        if any(chunk_documents.get(chunk_id) != expected_document for chunk_id in record["positive_chunks"]):
            raise ValueError(f"正例 Chunk 文档归属错误：{record['query_id']}")


# main 读取已导入 Chunk，并将 V2 Query 写入独立目录。
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, default=Path("tests/evaluation-version1/datasets/raw/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("tests/evaluation-version1/datasets/labels-v2/queries.jsonl"))
    parser.add_argument("--sources-per-category", type=int, default=20)
    args = parser.parse_args()

    profiles = legacy.load_profiles(args.mapping)
    records, selected = _build_records(profiles, args.sources_per_category)
    _validate_records(records, selected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"output={args.output} queries={len(records)} types={dict(Counter(row['query_type'] for row in records))}")


if __name__ == "__main__":
    main()
