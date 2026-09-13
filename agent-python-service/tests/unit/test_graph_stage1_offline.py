import tempfile
import unittest
from pathlib import Path

from familyos_agent.graph_rag.offline import build_recipe_graph_candidates, parse_recipe_markdown


class OfflineGraphStage1Test(unittest.TestCase):
    """验证 Markdown 菜谱离线实体关系候选生成。"""

    def test_extracts_ingredients_steps_and_relations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.md"
            path.write_text("# 番茄炒蛋\n\n## 必备原料和工具\n- 番茄\n- 鸡蛋（可选）\n\n## 操作\n1. 番茄切块\n2. 鸡蛋炒熟\n", encoding="utf-8")
            title, ingredients, steps = parse_recipe_markdown(path)
            self.assertEqual(title, "番茄炒蛋")
            self.assertEqual(ingredients, ["番茄", "鸡蛋"])
            self.assertEqual(len(steps), 2)
            entities, relations = build_recipe_graph_candidates(path)
            self.assertEqual(sum(item.entity_type == "Ingredient" for item in entities), 2)
            self.assertEqual(sum(item.relation_type == "PRECEDES" for item in relations), 1)


if __name__ == "__main__":
    unittest.main()
