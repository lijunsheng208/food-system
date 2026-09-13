import unittest

from familyos_agent.domain import ParentChunk
from familyos_agent.graph_rag import LLMGraphExtractor


class FakeModel:
    """返回固定抽取结果的同步模型。"""

    def invoke(self, messages):
        return {"content": '{"entities":[{"name":"鸡肉","type":"Ingredient","confidence":0.9},{"name":"西兰花","type":"Ingredient","confidence":0.4}],"relations":[]}'}


class GraphExtractorTest(unittest.TestCase):
    """验证 LLM 抽取结果的置信度过滤和来源绑定。"""

    def test_filters_low_confidence_entities(self):
        chunk = ParentChunk("p1", 1, 2, 3, 4, 0, "鸡肉和西兰花", "sha", {})
        entities, relations = LLMGraphExtractor(FakeModel(), 0.7).extract(chunk)
        self.assertEqual([entity.name for entity in entities], ["鸡肉"])
        self.assertEqual(relations, [])


if __name__ == "__main__":
    unittest.main()
