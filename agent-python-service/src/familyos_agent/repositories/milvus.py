"""Milvus 连接健康检查和文档 Chunk Collection 初始化。"""

from typing import Any, Dict, List, Optional, Sequence

from ..config import MilvusConfig
from ..domain import ChildChunk
from ..retrieval import EmbeddedChunks


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


class MilvusVectorRepository:
    """将 Chunk 向量以版本为单位幂等写入 Milvus。"""

    # 注入已完成健康检查的 Collection 管理器，复用其客户端。
    def __init__(self, manager: MilvusCollectionManager) -> None:
        self._manager = manager
        self._client = manager._client
        self._collection = manager._config.collection

    # 批量替换版本；先删除旧版本，主键 chunk_id 保证重复消息不会重复插入。
    def replace_version(self, document_id: int, index_version: int, chunks: Sequence[ChildChunk], embeddings: EmbeddedChunks) -> None:
        if not chunks or len(chunks) != len(embeddings.dense) or len(chunks) != len(embeddings.sparse):
            raise ValueError("Chunk 与 Dense/Sparse 向量数量不一致")
        for vector, weights in zip(embeddings.dense, embeddings.sparse):
            if len(vector) != self._manager._dimensions:
                raise ValueError("Dense 向量维度与 Milvus Collection 不一致")
            if not isinstance(weights, dict) or any(not isinstance(key, int) or not isinstance(value, (int, float)) for key, value in weights.items()):
                raise ValueError("Sparse 向量必须是 token_id 到权重的字典")
        self.delete_version(document_id, index_version)
        rows = []
        for chunk, dense, sparse in zip(chunks, embeddings.dense, embeddings.sparse):
            rows.append({"chunk_id": chunk.id, "document_id": chunk.document_id, "knowledge_base_id": chunk.knowledge_base_id, "user_id": chunk.user_id, "index_version": chunk.index_version, "chunk_index": chunk.index, "parent_id": chunk.parent_id, "content_sha256": chunk.content_sha256, "content": chunk.content, "metadata": chunk.metadata, "active": True, "dense_vector": list(dense), "sparse_vector": dict(sparse)})
        if rows:
            self._client.insert(collection_name=self._collection, data=rows)
        # MilvusClient 没有跨行 UPDATE 的稳定契约；旧版本在检索 filter 中排除，避免依赖非原子状态切换。

    # 删除指定文档版本，供失败补偿和重复消息清理使用。
    def delete_version(self, document_id: int, index_version: int) -> None:
        self._client.delete(collection_name=self._collection, filter="document_id == %d and index_version == %d" % (document_id, index_version))
