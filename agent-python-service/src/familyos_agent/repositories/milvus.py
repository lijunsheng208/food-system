"""Milvus 连接健康检查和文档 Chunk Collection 初始化。"""

from typing import Any, Dict, List, Optional

from ..config import MilvusConfig


EXPECTED_FIELDS = {
    "chunk_id",
    "document_id",
    "knowledge_base_id",
    "user_id",
    "index_version",
    "chunk_index",
    "parent_id",
    "content_sha256",
    "content",
    "metadata",
    "active",
    "dense_vector",
    "sparse_vector",
}


class MilvusCollectionManager:
    """负责 Milvus 启动探测以及 v1 Collection 的幂等创建和契约校验。"""

    # 初始化客户端；测试可注入兼容 MilvusClient 的对象，避免依赖外部服务。
    def __init__(self, config: MilvusConfig, dimensions: int, client: Optional[Any] = None) -> None:
        self._config = config
        self._dimensions = dimensions
        if client is None:
            try:
                from pymilvus import MilvusClient
            except ImportError as exc:
                raise RuntimeError("缺少 pymilvus，请重新安装 agent-python-service") from exc
            kwargs: Dict[str, Any] = {
                "uri": config.uri,
                "db_name": config.database,
                "timeout": config.timeout,
            }
            if config.token:
                kwargs["token"] = config.token
            client = MilvusClient(**kwargs)
        self._client = client

    # ensure_ready 先验证连接，再幂等创建或校验固定 Schema 的 Collection。
    def ensure_ready(self) -> None:
        try:
            self._client.list_collections(timeout=self._config.timeout)
            if self._client.has_collection(collection_name=self._config.collection, timeout=self._config.timeout):
                self._validate_collection()
                return
            self._create_collection()
        except Exception as exc:
            raise RuntimeError("Milvus 健康检查或 Collection 初始化失败") from exc

    # close 释放 Milvus SDK 持有的连接资源。
    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            close()

    # _create_collection 按评估稿创建 Dense/Sparse 共存且内容可直接召回的 Schema。
    def _create_collection(self) -> None:
        try:
            from pymilvus import DataType
        except ImportError as exc:
            raise RuntimeError("缺少 pymilvus，请重新安装 agent-python-service") from exc
        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("document_id", DataType.INT64)
        schema.add_field("knowledge_base_id", DataType.INT64)
        schema.add_field("user_id", DataType.INT64)
        schema.add_field("index_version", DataType.INT64)
        schema.add_field("chunk_index", DataType.INT32)
        schema.add_field("parent_id", DataType.VARCHAR, max_length=64)
        schema.add_field("content_sha256", DataType.VARCHAR, max_length=64)
        schema.add_field("content", DataType.VARCHAR, max_length=65535)
        schema.add_field("metadata", DataType.JSON)
        schema.add_field("active", DataType.BOOL)
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=self._dimensions)
        schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
        indexes = self._client.prepare_index_params()
        dense_params: Dict[str, Any] = {"metric_type": self._config.dense_metric_type}
        if self._config.dense_index_type == "HNSW":
            dense_params["params"] = {"M": 16, "efConstruction": 200}
        indexes.add_index(field_name="dense_vector", index_name="dense_vector_idx", index_type=self._config.dense_index_type, **dense_params)
        indexes.add_index(field_name="sparse_vector", index_name="sparse_vector_idx", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
        self._client.create_collection(
            collection_name=self._config.collection,
            schema=schema,
            index_params=indexes,
            consistency_level="Bounded",
            timeout=self._config.timeout,
        )

    # _validate_collection 阻止服务在字段缺失或 Embedding 维度不一致时继续启动。
    def _validate_collection(self) -> None:
        description = self._client.describe_collection(collection_name=self._config.collection, timeout=self._config.timeout)
        fields: List[Dict[str, Any]] = description.get("fields", [])
        names = {str(field.get("name")) for field in fields}
        if names != EXPECTED_FIELDS:
            raise ValueError("Milvus Collection 字段与 familyos_document_chunks_v1 契约不一致")
        dense = next(field for field in fields if field.get("name") == "dense_vector")
        params = dense.get("params") or dense.get("type_params") or {}
        if int(params.get("dim", 0)) != self._dimensions:
            raise ValueError("Milvus Dense 向量维度与 Embedding 配置不一致")
