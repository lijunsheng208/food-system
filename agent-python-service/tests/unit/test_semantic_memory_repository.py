import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from familyos_agent.config import MilvusConfig, SemanticMemoryConfig
from familyos_agent.repositories.semantic_memory import SEMANTIC_MEMORY_FIELDS, MilvusSemanticMemoryRepository
from familyos_agent.retrieval import EmbeddedChunks


class FakeDataType:
    """提供语义记忆 Collection 测试所需字段类型。"""

    VARCHAR = "VARCHAR"
    INT64 = "INT64"
    FLOAT = "FLOAT"
    BOOL = "BOOL"
    FLOAT_VECTOR = "FLOAT_VECTOR"


class FakeSchema:
    """记录语义记忆 Schema 字段。"""

    def __init__(self):
        """初始化字段记录。"""
        self.fields = []

    def add_field(self, name, data_type, **kwargs):
        """记录单个字段定义。"""
        self.fields.append((name, data_type, kwargs))


class FakeIndexes:
    """记录 Dense 索引定义。"""

    def __init__(self):
        """初始化索引记录。"""
        self.values = []

    def add_index(self, **kwargs):
        """记录单个索引定义。"""
        self.values.append(kwargs)


class FakeEmbedding:
    """返回固定二维 Dense 向量。"""

    def embed_documents(self, texts):
        """按输入数量返回固定向量。"""
        return EmbeddedChunks([[0.1, 0.2] for _ in texts], [{} for _ in texts])


class FakeClient:
    """模拟语义记忆 Milvus 读写和用户过滤。"""

    def __init__(self):
        """初始化调用记录与可配置搜索结果。"""
        self.schema = FakeSchema()
        self.indexes = FakeIndexes()
        self.created = None
        self.inserted = []
        self.search_results = [[]]
        self.search_calls = []
        self.query_results = []

    def has_collection(self, **kwargs):
        """默认表示 Collection 不存在。"""
        return False

    def create_schema(self, **kwargs):
        """返回字段记录器。"""
        return self.schema

    def prepare_index_params(self):
        """返回索引记录器。"""
        return self.indexes

    def create_collection(self, **kwargs):
        """记录 Collection 创建参数。"""
        self.created = kwargs

    def search(self, **kwargs):
        """记录向量检索条件并返回预设结果。"""
        self.search_calls.append(kwargs)
        return self.search_results

    def query(self, **kwargs):
        """返回精确哈希去重结果。"""
        return self.query_results

    def insert(self, **kwargs):
        """记录新增语义记忆。"""
        self.inserted.extend(kwargs["data"])


class SemanticMemoryRepositoryTest(unittest.TestCase):
    """验证独立 Collection、用户隔离、阈值召回和去重写入。"""

    def _repository(self, client):
        """构造使用二维向量的测试仓储。"""
        milvus = MilvusConfig("http://localhost:19530", "", "default", "familyos_document_chunks_v1", 10, "AUTOINDEX", "COSINE")
        memory = SemanticMemoryConfig(True, "familyos_user_semantic_memories_v1", 5, 0.45, 0.95)
        return MilvusSemanticMemoryRepository(client, milvus, memory, FakeEmbedding(), 2)

    def test_creates_independent_semantic_memory_collection(self):
        """语义记忆应创建独立于菜谱 Chunk 的固定 Schema。"""
        client = FakeClient()
        with patch.dict(sys.modules, {"pymilvus": SimpleNamespace(DataType=FakeDataType)}):
            self._repository(client).ensure_ready()

        self.assertEqual({field[0] for field in client.schema.fields}, SEMANTIC_MEMORY_FIELDS)
        self.assertEqual(client.created["collection_name"], "familyos_user_semantic_memories_v1")

    def test_recall_enforces_user_filter_and_score_threshold(self):
        """召回必须限定 user_id，并过滤低于相关度阈值的结果。"""
        client = FakeClient()
        client.search_results = [[
            {"distance": 0.8, "entity": {"memory_id": "m1", "memory_type": "habit", "content": "周日备餐", "importance": 0.9}},
            {"distance": 0.2, "entity": {"memory_id": "m2", "memory_type": "feedback", "content": "无关", "importance": 1.0}},
        ]]

        result = self._repository(client).recall(7, "今天怎么备餐")

        self.assertEqual([item["memory_id"] for item in result], ["m1"])
        self.assertIn("user_id == 7", client.search_calls[0]["filter"])

    def test_remember_skips_exact_duplicate(self):
        """同一用户相同文本应通过哈希直接去重且不重复向量化插入。"""
        client = FakeClient()
        client.query_results = [{"memory_id": "existing"}]

        inserted = self._repository(client).remember(7, "experience", "炒糖色失败过", 0.9)

        self.assertFalse(inserted)
        self.assertEqual(client.inserted, [])

    def test_remember_inserts_new_memory(self):
        """新的开放式经历应携带来源、用户和向量写入独立 Collection。"""
        client = FakeClient()

        inserted = self._repository(client).remember(7, "experience", "炒糖色失败过", 0.9, "c1", "r1")

        self.assertTrue(inserted)
        self.assertEqual(client.inserted[0]["user_id"], 7)
        self.assertEqual(client.inserted[0]["source_request_id"], "r1")
        self.assertEqual(client.inserted[0]["dense_vector"], [0.1, 0.2])


if __name__ == "__main__":
    unittest.main()
