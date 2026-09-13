"""阶段 1 离线图构建验证脚本，默认验证 HowToCook dishes Markdown。"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from familyos_agent.graph_rag.offline import build_recipe_graph_candidates, discover_markdown_files


def main() -> None:
    """扫描菜谱、生成图候选 JSONL，并输出阶段 1 质量统计。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="../../HowToCook-master/dishes")
    parser.add_argument("--output", default="evaluation/experiments/graph-stage1/candidates.jsonl")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.limit < 0:
        raise ValueError("limit 不能为负数")
    files = list(discover_markdown_files(Path(args.input).resolve(), args.limit))
    if not files:
        raise ValueError("未找到 Markdown 菜谱")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    rows = []
    for path in files:
        entities, relations = build_recipe_graph_candidates(path)
        counts.update([entity.entity_type for entity in entities])
        counts.update([relation.relation_type for relation in relations])
        rows.append({"source_file": str(path), "entities": [entity.__dict__ for entity in entities], "relations": [relation.__dict__ for relation in relations]})
    output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    summary = {"files": len(files), "recipes": counts["Recipe"], "ingredients": counts["Ingredient"], "steps": counts["CookingStep"], "relations": {key: counts[key] for key in ("REQUIRES", "CONTAINS_STEP", "PRECEDES")}, "output": str(output)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
