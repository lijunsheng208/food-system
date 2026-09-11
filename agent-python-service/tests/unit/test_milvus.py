"""Milvus Collection 初始化的无外部服务单元测试。"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from familyos_agent.config import MilvusConfig
from familyos_agent.repositories.milvus import EXPECTED_FIELDS, MilvusCollectionManager


class FakeDataType:
    """提供 Schema 构建测试需要的 pymilvus 字段类型常量。"""

    VARCHAR = "VARCHAR"
    INT64 = "INT64"
    INT32 = "INT32"
    JSON = "JSON"
    BOOL = "BOOL"
    FLOAT_VECTOR = "FLOAT_VECTOR"
    SPARSE_FLOAT_VECTOR = "SPARSE_FLOAT_VECTOR"


class FakeSchema:
    """记录 Collection Schema 添加的字段。"""

    # 初始化字段记录列表。
    def __init__(self) -> None:
        self.fields = []

    # 记录字段名称、类型和参数，模拟 pymilvus SchemaBuilder。
    def add_field(self, name, data_type, **kwargs) -> None:
        self.fields.append((name, data_type, kwargs))


class FakeIndexes:
    """记录 Dense 和 Sparse 索引参数。"""

    # 初始化索引记录列表。
    def __init__(self) -> None:
        self.values = []

    # 记录单个索引参数，模拟 pymilvus IndexParams。
    def add_index(self, **kwargs) -> None:
        self.values.append(kwargs)


class FakeMilvusClient:
    """模拟 Collection 不存在时的 MilvusClient。"""

    # 初始化 Schema、索引和创建请求记录。
    def __init__(self) -> None:
        self.schema = FakeSchema()
        self.indexes = FakeIndexes()
        self.created = None

    # 返回空 Collection 列表，表示健康检查成功。
    def list_collections(self, **_kwargs):
        return []

    # 返回 Collection 是否存在。
    def has_collection(self, **_kwargs):
        return False

    # 返回用于记录字段的 SchemaBuilder。
    def create_schema(self, **_kwargs):
        return self.schema

    # 返回用于记录索引的 IndexParams。
    def prepare_index_params(self):
        return self.indexes

    # 记录最终 Collection 创建参数。
    def create_collection(self, **kwargs) -> None:
        self.created = kwargs


class MilvusCollectionManagerTest(unittest.TestCase):
    """验证 Collection 幂等初始化和不兼容 Schema 的快速失败。"""

    # 构造测试使用的固定 Milvus 配置。
    def _config(self) -> MilvusConfig:
        return MilvusConfig("http://localhost:19530", "", "default", "familyos_document_chunks_v1", 10, "AUTOINDEX", "COSINE")

    # Collection 不存在时应创建设计稿要求的全部字段和两个向量索引。
    def test_creates_expected_collection(self) -> None:
        client = FakeMilvusClient()
        with patch.dict(sys.modules, {"pymilvus": SimpleNamespace(DataType=FakeDataType)}):
            MilvusCollectionManager(self._config(), 1536, client).ensure_ready()
        self.assertEqual({field[0] for field in client.schema.fields}, EXPECTED_FIELDS)
        self.assertEqual({item["field_name"] for item in client.indexes.values}, {"dense_vector", "sparse_vector"})
        self.assertEqual(client.created["collection_name"], "familyos_document_chunks_v1")

    # 已存在 Collection 的 Dense 维度不一致时必须阻止服务启动。
    def test_rejects_existing_collection_with_wrong_dimension(self) -> None:
        client = FakeMilvusClient()
        client.has_collection = lambda **_kwargs: True
        client.describe_collection = lambda **_kwargs: {
            "fields": [
                {"name": name, "params": {"dim": 8} if name == "dense_vector" else {}}
                for name in EXPECTED_FIELDS
            ]
        }
        with self.assertRaisesRegex(RuntimeError, "Collection 初始化失败"):
            MilvusCollectionManager(self._config(), 1536, client).ensure_ready()


if __name__ == "__main__":
    unittest.main()
