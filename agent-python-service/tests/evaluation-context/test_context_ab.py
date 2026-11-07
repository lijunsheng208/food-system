"""验证信息保留基准的布局、信息单元计数和更正一致性。"""

import importlib.util
import json
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).with_name("run_context_ab.py")
SPEC = importlib.util.spec_from_file_location("run_context_ab", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ContextInformationTest(unittest.TestCase):
    """确保评测只衡量上下文信息保留与压缩收益。"""

    def test_history_contains_recent_and_older_facts(self):
        """验证事实同时分布于最近窗口和较早历史。"""
        dataset = MODULE.json.loads(MODULE.DATASET_PATH.read_text(encoding="utf-8"))
        answerable = [item for item in dataset if item.get("answerable", True)]
        history = MODULE._build_history(answerable)
        recent_text = "\n".join(str(item["content"]) for item in history[-12:])
        older_text = "\n".join(str(item["content"]) for item in history[:-12])

        self.assertEqual(len(dataset), 36)
        self.assertEqual(len(answerable), 31)
        self.assertEqual(sum(bool(item.get("recent_group")) for item in answerable), 11)
        for item in answerable:
            if item.get("recent_group"):
                self.assertIn(item["history_user"], recent_text)
            else:
                self.assertIn(item["history_user"], older_text)
                self.assertNotIn(item["history_user"], recent_text)

    def test_information_units_require_source_coverage(self):
        """验证实体与属性按独立信息单元计算。"""
        text = "我对花生严重过敏，推荐菜时避开花生和花生油。"
        entities = [[term] for term in MODULE.ENTITY_TERMS["allergy_peanut"]]
        details = [["花生"]]

        self.assertEqual(MODULE._group_hits(text, entities), 2)
        self.assertEqual(MODULE._group_hits(text, details), 1)
        self.assertEqual(MODULE._group_hits("只有花生", entities), 1)

    def test_information_metrics_use_information_units_not_answers(self):
        """验证汇总只依赖上下文里的信息单元而非问答结果。"""
        cases = [{
            "category": "更正与冲突", "entities": [["家"]], "details": [["四"]],
            "entities_total": 1, "details_total": 1, "information_total": 2,
            "fixed_entities_retained": 0, "fixed_details_retained": 0,
            "compressed_entities_retained": 1, "compressed_details_retained": 1,
            "fixed_information_retained": 0, "compressed_information_retained": 2,
            "fixed_stale_values": 1, "compressed_stale_values": 0,
            "forbidden_terms": ["三"],
        }]
        methods, categories = MODULE._score_information(cases)

        self.assertEqual(methods["fixed_window"]["information_recall"], 0.0)
        self.assertEqual(methods["rolling_summary"]["information_recall"], 1.0)
        self.assertEqual(categories["更正与冲突"]["compressed_information_recall"], 1.0)

    def test_relation_complete_rejects_cross_fact_keyword_matches(self):
        """验证实体与属性分散在不同条目时不能算作关系完整。"""
        relation_terms = [["小满"], ["花生"], ["起疹子"]]

        self.assertFalse(MODULE._fact_relation_complete("小满喜欢散步。花生会起疹子。", relation_terms))
        self.assertTrue(MODULE._fact_relation_complete("小满吃花生会起疹子。", relation_terms))

    def test_stress_dataset_keeps_expected_scale_and_boundaries(self):
        """验证压力集规模、近期窗口分布和更正样本不会意外退化。"""
        dataset_path = Path(__file__).with_name("dataset_stress_112.json")
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        answerable = [item for item in dataset if item.get("answerable", True)]

        self.assertEqual(len(dataset), 112)
        self.assertEqual(len(answerable), 110)
        self.assertEqual(sum(bool(item.get("recent_group")) for item in answerable), 20)
        self.assertEqual(sum(bool(item.get("forbidden_terms")) for item in answerable), 10)
        self.assertTrue(all(item.get("entity_terms") for item in answerable))
        self.assertTrue(all(item.get("relation_terms") for item in answerable))

    def test_correction_consistency_requires_latest_value_without_stale_value(self):
        """验证更正一致性要求新值完整且不包含旧值。"""
        cases = [{"forbidden_terms": ["三"], "fixed_details_retained": 1, "details_total": 1,
                  "fixed_stale_values": 0},
                 {"forbidden_terms": ["旧"], "fixed_details_retained": 1, "details_total": 1,
                  "fixed_stale_values": 1}]
        metrics = MODULE._correction_metrics(cases, "fixed")

        self.assertEqual(metrics["corrections_total"], 2)
        self.assertEqual(metrics["latest_values_retained"], 2)
        self.assertEqual(metrics["stale_values_retained"], 1)

    def test_strict_metrics_do_not_call_keyword_hits_lossless(self):
        """验证事实完整与更正安全需要分别满足完整字段和无旧值。"""
        cases = [{
            "entities_total": 2, "details_total": 2, "forbidden_terms": ["周四"],
            "fixed_entities_retained": 2, "fixed_details_retained": 2, "fixed_stale_values": 1,
            "compressed_entities_retained": 1, "compressed_details_retained": 2, "compressed_stale_values": 0,
        }]

        fixed = MODULE._strict_metrics(cases, "fixed")
        compressed = MODULE._strict_metrics(cases, "compressed")

        self.assertEqual(fixed["fact_complete_rate"], 1.0)
        self.assertEqual(fixed["correction_safety_rate"], 0.0)
        self.assertEqual(compressed["fact_complete_rate"], 0.0)
        self.assertEqual(compressed["correction_safety_rate"], 1.0)
        self.assertLess(compressed["fact_complete_ci95"][0], 1.0)
        self.assertGreater(compressed["fact_complete_ci95"][1], 0.0)


if __name__ == "__main__":
    unittest.main()
