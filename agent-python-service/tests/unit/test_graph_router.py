"""验证阶段 4 受控路由、组合检索和异常回退。"""

import time
import unittest

from familyos_agent.graph_rag import ControlledRetriever
from familyos_agent.retrieval import RetrievedChunk


class FakeVector:
    """返回一个可引用向量检索结果。"""

    def retrieve(self, query):
        return [RetrievedChunk("v1", 1, query.knowledge_base_id, query.index_version, "p1", "原文", 1.0, {})]


class FakeGraph:
    """返回图结果和同一来源证据。"""

    def retrieve(self, *args):
        return {"results": [{"source_chunk_id": "g1"}], "evidence": []}


class GraphRouterTest(unittest.TestCase):
    """覆盖普通、关系和实时查询分支。"""

    def test_vector_route_keeps_normal_queries(self):
        result = ControlledRetriever(FakeVector()).retrieve("番茄炒蛋怎么做", 1, 2)
        self.assertEqual(result["route_strategy"], "vector")
        self.assertEqual(result["documents"][0].chunk_id, "v1")

    def test_graph_route_falls_back_to_vector_on_empty_graph(self):
        result = ControlledRetriever(FakeVector(), FakeGraph()).retrieve("番茄炒蛋需要哪些食材", 1, 2)
        self.assertEqual(result["route_strategy"], "graph")
        self.assertEqual(result["documents"][0].chunk_id, "v1")

    def test_tool_failure_does_not_break_vector_fallback(self):
        def failed_tool(*args):
            raise RuntimeError("unavailable")

        result = ControlledRetriever(FakeVector(), tool_resolver=failed_tool).retrieve("今天有什么实时库存", 1, 2)
        self.assertEqual(result["route_strategy"], "tool")
        self.assertEqual(result["fallback_reason"], "TOOL_UNAVAILABLE")
        self.assertEqual(result["documents"][0].chunk_id, "v1")


if __name__ == "__main__":
    unittest.main()
