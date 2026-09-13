import unittest

from familyos_agent.graph_rag import Evidence, GraphQueryPlan, GraphQueryType, GraphRelation


class GraphRagModelsTest(unittest.TestCase):
    """验证阶段 0 图 RAG 契约的边界校验。"""

    def test_relation_type_must_be_allowlisted(self):
        with self.assertRaises(ValueError):
            GraphRelation("r1", "INVENTED", "a", "b", 1, 2, 3, 1, "c1")

    def test_query_plan_limits_depth_and_relations(self):
        plan = GraphQueryPlan(GraphQueryType.MULTI_HOP, ["鸡肉"], max_depth=3)
        self.assertEqual(plan.max_depth, 3)
        with self.assertRaises(ValueError):
            GraphQueryPlan(GraphQueryType.MULTI_HOP, ["鸡肉"], max_depth=4)

    def test_evidence_requires_supported_source_and_content(self):
        evidence = Evidence("graph", "鸡肉 -> 西兰花", 1, 2)
        self.assertEqual(evidence.source_type, "graph")
        with self.assertRaises(ValueError):
            Evidence("unknown", "内容", 1, 2)


if __name__ == "__main__":
    unittest.main()
