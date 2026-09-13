"""验证阶段 3 只读图检索的权限参数和证据回查。"""

import unittest

from familyos_agent.graph_rag import GraphRetriever
from familyos_agent.graph_rag.models import GraphQueryPlan, GraphQueryType


class FakeGraphRepository:
    """记录检索参数并返回最小化图结果。"""

    def search_entity_relations(self, *args):
        return [{"source_chunk_id": "c1", "name": "鸡蛋"}]

    def search_paths(self, *args):
        return [{"source_chunk_id": "c1", "path": "菜谱-需要-鸡蛋"}]

    def search_subgraph(self, *args):
        return [{"source_chunk_id": "c1", "path": "子图"}]

    def resolve_evidence(self, *args):
        return [{"source_chunk_id": "c1", "document_id": 1, "index_version": 2}]


class GraphRetrieverTest(unittest.TestCase):
    """覆盖三种只读检索和来源回查。"""

    def test_retrieve_entity_relation_and_resolve_content(self):
        retriever = GraphRetriever(FakeGraphRepository(), lambda *args: [{"chunk_id": "c1", "content": "菜谱原文"}])
        plan = GraphQueryPlan(GraphQueryType.ENTITY_RELATION, ["番茄炒蛋"], max_nodes=10)
        result = retriever.retrieve(plan, 3, 4, 2)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["evidence"][0].content, "菜谱原文")
        self.assertEqual(result["evidence"][0].user_id, 3)

    def test_multi_hop_uses_path_query(self):
        retriever = GraphRetriever(FakeGraphRepository())
        plan = GraphQueryPlan(GraphQueryType.MULTI_HOP, ["番茄炒蛋"], max_depth=2, max_nodes=10)
        self.assertEqual(retriever.retrieve(plan, 3, 4, resolve_evidence=False)["results"][0]["path"], "菜谱-需要-鸡蛋")


if __name__ == "__main__":
    unittest.main()
