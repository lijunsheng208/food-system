import unittest
from types import SimpleNamespace

from familyos_agent.domain import ChildChunk
from familyos_agent.repositories.milvus import MilvusVectorRepository
from familyos_agent.retrieval import EmbeddedChunks


class FakeMilvusClient:
    """记录 Milvus 写入调用，验证 Repository 的幂等边界。"""

    def __init__(self):
        self.deleted = []
        self.inserted = []

    def delete(self, **kwargs):
        self.deleted.append(kwargs)

    def insert(self, **kwargs):
        self.inserted.extend(kwargs["data"])


class MilvusRepositoryTest(unittest.TestCase):
    # 构造固定的子块，避免测试依赖解析器和数据库。
    def _chunk(self):
        return ChildChunk("chunk-1", "parent-1", 1, 2, 3, 4, 0, "正文", "a" * 64, {})

    def test_replace_deletes_version_before_insert(self):
        client = FakeMilvusClient()
        manager = SimpleNamespace(_client=client, _config=SimpleNamespace(collection="chunks"), _dimensions=2)
        repository = MilvusVectorRepository(manager)
        repository.replace_version(1, 4, [self._chunk()], EmbeddedChunks([[0.1, 0.2]], [{12: 0.5}]))
        self.assertEqual(len(client.deleted), 1)
        self.assertEqual(len(client.inserted), 1)
        self.assertEqual(client.inserted[0]["chunk_id"], "chunk-1")

    def test_rejects_wrong_dense_dimension_before_delete(self):
        client = FakeMilvusClient()
        manager = SimpleNamespace(_client=client, _config=SimpleNamespace(collection="chunks"), _dimensions=2)
        repository = MilvusVectorRepository(manager)
        with self.assertRaises(ValueError):
            repository.replace_version(1, 4, [self._chunk()], EmbeddedChunks([[0.1]], [{12: 0.5}]))
        self.assertEqual(client.deleted, [])


if __name__ == "__main__":
    unittest.main()
