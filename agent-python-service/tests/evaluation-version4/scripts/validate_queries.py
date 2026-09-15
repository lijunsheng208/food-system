"""校验 V4 Query 配额以及 Document/Parent/Child Gold 层级关系。"""

import argparse
import json
from pathlib import Path

from generate_queries import _load_profiles, validate_chunk_gold, validate_records


# _load_queries 读取 V4 Query JSONL。
def _load_queries(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# main 执行结构校验，并可阻止未人工审核的数据进入正式评测。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, default=Path("tests/evaluation-version1/datasets/raw/chunks.jsonl"))
    parser.add_argument("--queries", type=Path, default=Path("tests/evaluation-version4/datasets/queries.jsonl"))
    parser.add_argument("--chunk-gold", type=Path, default=Path("tests/evaluation-version4/datasets/chunk_gold.jsonl"))
    parser.add_argument("--require-reviewed", action="store_true")
    args = parser.parse_args()

    profiles = _load_profiles(args.mapping)
    queries = _load_queries(args.queries)
    summary = validate_records(queries, profiles)
    chunk_gold = _load_queries(args.chunk_gold)
    summary.update(validate_chunk_gold(chunk_gold, queries, profiles))
    if args.require_reviewed:
        pending = [query["query_id"] for query in queries if query.get("label_status") != "reviewed"]
        if pending:
            raise ValueError(f"仍有 {len(pending)} 条 Query 未人工审核")
        pending_gold = [item["query_id"] for item in chunk_gold if item.get("label_status") != "reviewed"]
        if pending_gold:
            raise ValueError(f"仍有 {len(pending_gold)} 条 Chunk Gold 未人工审核")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
