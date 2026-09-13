"""验证 LLM 意图输出到统一 RetrievalPlan 的转换。"""

import unittest

from familyos_agent.graph_rag import LLMIntentClassifier


class FakeModel:
    """返回固定 JSON 的同步模型。"""

    def __init__(self, content):
        self.content = content

    def invoke(self, messages):
        return {"content": self.content}


class IntentClassifierTest(unittest.TestCase):
    """覆盖三种路由及不可信图计划的降级。"""

    def test_vector_plan(self):
        plan = LLMIntentClassifier(FakeModel('{"route":"vector","vector_query":"番茄炒蛋做法"}')).classify("怎么做")
        self.assertEqual(plan.route, "vector")
        self.assertIsNone(plan.graph_plan)

    def test_hybrid_plan_contains_graph(self):
        plan = LLMIntentClassifier(FakeModel('{"route":"hybrid","vector_query":"红烧肉做法","graph":{"query_type":"entity_relation","source_entities":["红烧肉"]}}')).classify("红烧肉需要什么")
        self.assertEqual(plan.route, "hybrid")
        self.assertEqual(plan.graph_plan.source_entities, ["红烧肉"])

    def test_missing_entity_downgrades_vector(self):
        plan = LLMIntentClassifier(FakeModel('{"route":"graph","graph":{"query_type":"entity_relation","source_entities":[]}}')).classify("需要哪些食材")
        self.assertEqual(plan.route, "vector")

    def test_invalid_json_falls_back_vector(self):
        plan = LLMIntentClassifier(FakeModel("not-json")).classify("普通问题")
        self.assertEqual(plan.route, "vector")
        self.assertEqual(plan.vector_query, "普通问题")


if __name__ == "__main__":
    unittest.main()
