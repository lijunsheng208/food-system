"""验证阶段 4 受控路由、组合检索和异常回退。"""

import time
import unittest

from familyos_agent.graph_rag import ControlledRetriever, GraphQueryPlan, GraphQueryType, RetrievalPlan
from familyos_agent.retrieval import RetrievedChunk


class FakeVector:
    """返回一个可引用向量检索结果。"""

    def __init__(self):
        self.query_text = ""

    def retrieve(self, query):
        self.query_text = query.text
        return [RetrievedChunk("v1", 1, query.knowledge_base_id, query.index_version, "p1", "原文", 1.0, {})]


class FakeGraph:
    """返回图结果和同一来源证据。"""

    def retrieve(self, *args):
        return {"results": [{"source_chunk_id": "g1"}], "evidence": []}


class FakeGraphEvidence(FakeGraph):
    """返回带 canonical chunk_id 的图证据。"""

    def retrieve(self, *args):
        return {"results": [{"source_chunk_id": "g1"}], "evidence": [{"chunk_id": "g1", "content": "图证据"}]}


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

    def test_llm_vector_plan_does_not_call_graph(self):
        graph = FakeGraphEvidence()
        vector = FakeVector()
        plan = RetrievalPlan("vector", "改写后的查询")
        result = ControlledRetriever(vector, graph).retrieve("原问题", 1, 2, plan=plan)
        self.assertEqual(result["route_strategy"], "vector")
        self.assertEqual(result["documents"][0].chunk_id, "v1")
        self.assertEqual(result["graph_results"], [])
        self.assertEqual(vector.query_text, "原问题")

    def test_hybrid_plan_deduplicates_canonical_chunk(self):
        graph = FakeGraphEvidence()
        vector = FakeVector()
        graph_plan = GraphQueryPlan(GraphQueryType.ENTITY_RELATION, ["番茄炒蛋"])
        result = ControlledRetriever(vector, graph).retrieve("原问题", 1, 2, plan=RetrievalPlan("hybrid", "改写后的查询", graph_plan))
        self.assertEqual(result["route_strategy"], "hybrid")
        self.assertEqual([item["chunk_id"] if isinstance(item, dict) else item.chunk_id for item in result["documents"]], ["g1", "v1"])
        self.assertEqual(vector.query_text, "改写后的查询")


if __name__ == "__main__":
    unittest.main()
