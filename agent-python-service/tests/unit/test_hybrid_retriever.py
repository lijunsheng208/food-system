import unittest

from familyos_agent.retrieval import EmbeddedChunks, MilvusHybridRetriever, MilvusParentChildRetriever, RetrievalQuery, RetrievedChunk


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


class FakeBaseRetriever:
    """记录父子检索传给首轮检索器的 TopK。"""

    # 初始化固定的 Child 初召回结果。
    def __init__(self):
        self.top_k = 0

    # retrieve 返回两个相关 Parent 的首轮 Child。
    def retrieve(self, query):
        self.top_k = query.top_k
        return [
            RetrievedChunk("c1", 1, 2, 3, "p1", "普通内容", 0.9, {}),
            RetrievedChunk("c3", 2, 2, 3, "p2", "次相关内容", 0.8, {}),
        ]


class FakeParentClient:
    """模拟按 Parent ID 查询全部兄弟 Child 的 Milvus 客户端。"""

    # 初始化查询表达式记录。
    def __init__(self):
        self.expression = ""

    # query 返回重复的首轮 Child 和新增兄弟 Child。
    def query(self, **kwargs):
        self.expression = kwargs["filter"]
        return [
            {"chunk_id": "c1", "document_id": 1, "knowledge_base_id": 2, "index_version": 3, "parent_id": "p1", "content": "普通内容", "metadata": {}},
            {"chunk_id": "c2", "document_id": 1, "knowledge_base_id": 2, "index_version": 3, "parent_id": "p1", "content": "最相关答案", "metadata": {}},
        ]


class FakeReranker:
    """按文本内容返回固定 Cross-Encoder 分数。"""

    # score 保留输入顺序并让兄弟 Child 获得最高分。
    def score(self, query, chunks):
        scores = {"普通内容": 0.1, "次相关内容": 0.5, "最相关答案": 0.95}
        return [scores[chunk] for chunk in chunks]


class ParentChildRetrieverTest(unittest.TestCase):
    """验证父子候选扩展、权限过滤、去重和 Cross-Encoder 排序。"""

    # 首轮应召回 50 个 Child，扩展同 Parent Child 后按重排分数返回最终 Top2。
    def test_expands_parent_children_and_reranks(self):
        base = FakeBaseRetriever()
        client = FakeParentClient()
        retriever = MilvusParentChildRetriever(base, client, "chunks", FakeReranker(), recall_top_k=50)

        rows = retriever.retrieve(RetrievalQuery("目标问题", 2, 9, 2, (1, 2), 3))

        self.assertEqual(base.top_k, 50)
        self.assertEqual([row.chunk_id for row in rows], ["c2", "c3"])
        self.assertEqual(rows[0].score, 0.95)
        self.assertIn('parent_id in ["p1", "p2"]', client.expression)
        self.assertIn("user_id == 9", client.expression)
        self.assertIn("knowledge_base_id == 2", client.expression)
        self.assertIn("index_version == 3", client.expression)
        self.assertIn("document_id in [1, 2]", client.expression)

    # 初召回数量超出约定范围时应在启动阶段快速失败。
    def test_rejects_invalid_recall_top_k(self):
        with self.assertRaisesRegex(ValueError, "20 到 100"):
            MilvusParentChildRetriever(FakeBaseRetriever(), FakeParentClient(), "chunks", FakeReranker(), recall_top_k=10)

    # 验证扩大到 100 个首轮候选后仍可构造父子检索器。
    def test_accepts_recall_top_k_100(self):
        retriever = MilvusParentChildRetriever(FakeBaseRetriever(), FakeParentClient(), "chunks", FakeReranker(), recall_top_k=100)
        self.assertIsNotNone(retriever)


if __name__ == "__main__":
    unittest.main()
