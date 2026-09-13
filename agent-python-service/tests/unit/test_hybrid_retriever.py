import unittest

from familyos_agent.retrieval import EmbeddedChunks, MilvusHybridRetriever, RetrievalQuery


class FakeEmbedding:
    # 返回固定查询向量，隔离模型调用。
    def embed_documents(self, texts):
        return EmbeddedChunks([[0.1, 0.2]], [{1: 0.8}])


class FakeClient:
    # 模拟 Milvus 原生 Hybrid Search，并记录两路召回请求。
    def __init__(self):
        self.requests = []
        self.limit = 0

    def hybrid_search(self, collection, requests, ranker, **kwargs):
        self.requests = requests
        self.limit = kwargs["limit"]
        return [[
            {"entity": {"chunk_id": "b", "document_id": 2, "knowledge_base_id": 2, "index_version": 3, "parent_id": "p2", "content": "数字 42", "metadata": {}}, "distance": .9},
            {"entity": {"chunk_id": "a", "document_id": 1, "knowledge_base_id": 2, "index_version": 3, "parent_id": "p", "content": "同义内容", "metadata": {}}, "distance": .8},
        ]]


class HybridRetrieverTest(unittest.TestCase):
    # 验证权限、版本和文档过滤会同时应用，且 RRF 优先共同召回结果。
    def test_filters_and_rrf(self):
        client = FakeClient()
        retriever = MilvusHybridRetriever(client, "chunks", FakeEmbedding(), 2)
        rows = retriever.retrieve(RetrievalQuery("问题", 2, 9, 2, (1, 2), 3))
        self.assertEqual(rows[0].chunk_id, "b")
        self.assertEqual(client.limit, 2)
        self.assertEqual([request._anns_field for request in client.requests], ["dense_vector", "sparse_vector"])
        self.assertTrue(all(request._limit == 50 for request in client.requests))
        self.assertTrue(all("user_id == 9" in request._expr and "index_version == 3" in request._expr and "document_id in [1, 2]" in request._expr for request in client.requests))


if __name__ == "__main__":
    unittest.main()
