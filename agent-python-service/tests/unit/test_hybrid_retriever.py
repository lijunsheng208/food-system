import unittest

from familyos_agent.retrieval import EmbeddedChunks, MilvusHybridRetriever, RetrievalQuery


class FakeEmbedding:
    # 返回固定查询向量，隔离模型调用。
    def embed_documents(self, texts):
        return EmbeddedChunks([[0.1, 0.2]], [{1: 0.8}])


class FakeClient:
    # 按向量类型返回预设候选，并记录权限过滤条件。
    def __init__(self):
        self.filters = []

    def search(self, **kwargs):
        self.filters.append(kwargs["filter"])
        if kwargs["anns_field"] == "dense_vector":
            return [[{"chunk_id": "a", "document_id": 1, "knowledge_base_id": 2, "index_version": 3, "parent_id": "p", "content": "同义内容", "metadata": {}, "distance": .9}, {"chunk_id": "b", "document_id": 2, "knowledge_base_id": 2, "index_version": 3, "parent_id": "p2", "content": "数字 42", "metadata": {}, "distance": .8}]]
        return [[{"chunk_id": "b", "document_id": 2, "knowledge_base_id": 2, "index_version": 3, "parent_id": "p2", "content": "数字 42", "metadata": {}, "distance": .7}]]


class HybridRetrieverTest(unittest.TestCase):
    # 验证权限、版本和文档过滤会同时应用，且 RRF 优先共同召回结果。
    def test_filters_and_rrf(self):
        client = FakeClient()
        retriever = MilvusHybridRetriever(client, "chunks", FakeEmbedding(), 2)
        rows = retriever.retrieve(RetrievalQuery("问题", 2, 9, 2, (1, 2), 3))
        self.assertEqual(rows[0].chunk_id, "b")
        self.assertTrue(all("user_id == 9" in value and "index_version == 3" in value and "document_id in [1, 2]" in value for value in client.filters))


if __name__ == "__main__":
    unittest.main()
