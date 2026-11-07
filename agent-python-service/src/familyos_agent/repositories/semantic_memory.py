"""用户长期语义记忆的独立 Milvus Collection 与向量读写。"""

from __future__ import annotations

import hashlib
import math
import time
import uuid
from typing import Any, Mapping

from ..config import MilvusConfig, SemanticMemoryConfig


SEMANTIC_MEMORY_FIELDS = {
    "memory_id", "user_id", "memory_type", "content", "content_sha256", "importance",
    "source_conversation_id", "source_request_id", "created_at_epoch", "active", "dense_vector",
}
_MEMORY_TYPES = {"experience", "feedback", "habit", "history_issue"}


class MilvusSemanticMemoryRepository:
    """创建并访问用户专属语义记忆 Collection，禁止与知识库 Chunk 混存。"""

    # 复用文档 Milvus 客户端和 Embedding 模型，同时使用独立 Collection 契约。
    def __init__(
        self,
        client: Any,
        milvus_config: MilvusConfig,
        memory_config: SemanticMemoryConfig,
        embedding_client: Any,
        dimensions: int,
    ) -> None:
        if client is None or embedding_client is None or dimensions <= 0 or not memory_config.collection:
            raise ValueError("语义记忆仓储配置无效")
        self._client = client
        self._milvus_config = milvus_config
        self._config = memory_config
        self._embedding = embedding_client
        self._dimensions = dimensions

    # 验证连接后幂等创建语义记忆 Collection，并拒绝复用不兼容的既有 Schema。
    def ensure_ready(self) -> None:
        try:
            if self._client.has_collection(collection_name=self._config.collection, timeout=self._milvus_config.timeout):
                self._validate_collection()
                return
            self._create_collection()
        except Exception as exc:
            raise RuntimeError("语义记忆 Collection 初始化失败") from exc

    # 创建只包含 Dense 向量的用户记忆 Collection，语义内容不参与菜谱 BM25 检索。
    def _create_collection(self) -> None:
        try:
            from pymilvus import DataType
        except ImportError as exc:
            raise RuntimeError("缺少 pymilvus，请重新安装 agent-python-service") from exc
        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("memory_id", DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field("user_id", DataType.INT64)
        schema.add_field("memory_type", DataType.VARCHAR, max_length=32)
        schema.add_field("content", DataType.VARCHAR, max_length=2048)
        schema.add_field("content_sha256", DataType.VARCHAR, max_length=64)
        schema.add_field("importance", DataType.FLOAT)
        schema.add_field("source_conversation_id", DataType.VARCHAR, max_length=64)
        schema.add_field("source_request_id", DataType.VARCHAR, max_length=64)
        schema.add_field("created_at_epoch", DataType.INT64)
        schema.add_field("active", DataType.BOOL)
        schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=self._dimensions)
        indexes = self._client.prepare_index_params()
        dense_params: dict[str, Any] = {"metric_type": self._milvus_config.dense_metric_type}
        if self._milvus_config.dense_index_type == "HNSW":
            dense_params["params"] = {"M": 16, "efConstruction": 200}
        indexes.add_index(
            field_name="dense_vector", index_name="semantic_memory_dense_idx",
            index_type=self._milvus_config.dense_index_type, **dense_params,
        )
        self._client.create_collection(
            collection_name=self._config.collection,
            schema=schema,
            index_params=indexes,
            consistency_level="Bounded",
            timeout=self._milvus_config.timeout,
        )

    # 校验字段集合和向量维度，防止错误 Collection 导致跨业务数据混用。
    def _validate_collection(self) -> None:
        description = self._client.describe_collection(
            collection_name=self._config.collection, timeout=self._milvus_config.timeout,
        )
        fields = description.get("fields", [])
        if {str(field.get("name")) for field in fields} != SEMANTIC_MEMORY_FIELDS:
            raise ValueError("语义记忆 Collection 字段契约不一致")
        dense = next(field for field in fields if field.get("name") == "dense_vector")
        params = dense.get("params") or dense.get("type_params") or {}
        if int(params.get("dim", 0)) != self._dimensions:
            raise ValueError("语义记忆向量维度与 Embedding 配置不一致")

    # 在当前用户范围内召回与问题相关且超过阈值的开放式历史，绝不跨用户返回结果。
    def recall(self, user_id: int, query: str) -> list[dict[str, Any]]:
        if user_id <= 0 or not query.strip():
            return []
        vector = self._dense_vector(query)
        rows = self._client.search(
            collection_name=self._config.collection,
            data=[vector],
            anns_field="dense_vector",
            filter="user_id == %d and active == true" % user_id,
            limit=self._config.recall_top_k,
            output_fields=["memory_id", "memory_type", "content", "importance", "created_at_epoch"],
            search_params={"metric_type": self._milvus_config.dense_metric_type},
        )
        results = rows[0] if rows else []
        memories = []
        for row in results:
            score = float(row.get("distance", 0.0) if isinstance(row, Mapping) else getattr(row, "distance", 0.0))
            if score < self._config.minimum_score:
                continue
            entity = row.get("entity", row) if isinstance(row, Mapping) else getattr(row, "entity", {})
            item = dict(entity or {})
            memories.append({
                "memory_id": str(item.get("memory_id", "")),
                "memory_type": str(item.get("memory_type", "")),
                "content": str(item.get("content", "")),
                "importance": float(item.get("importance", 0.0)),
                "score": score,
            })
        memories.sort(key=lambda item: (-(0.8 * item["score"] + 0.2 * item["importance"]), item["memory_id"]))
        return memories

    # 向量化并保存本轮新经历；相同文本使用哈希去重，相近记忆使用高阈值语义去重。
    def remember(
        self,
        user_id: int,
        memory_type: str,
        content: str,
        importance: float,
        conversation_id: str = "",
        request_id: str = "",
    ) -> bool:
        if user_id <= 0 or memory_type not in _MEMORY_TYPES or not content.strip() or len(content) > 500 or not 0 <= importance <= 1:
            raise ValueError("语义记忆参数无效")
        content = content.strip()
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        exact = self._client.query(
            collection_name=self._config.collection,
            filter='user_id == %d and content_sha256 == "%s" and active == true' % (user_id, content_sha256),
            output_fields=["memory_id"],
            limit=1,
        )
        if exact:
            return False
        vector = self._dense_vector(content)
        similar = self._client.search(
            collection_name=self._config.collection,
            data=[vector], anns_field="dense_vector",
            filter="user_id == %d and active == true" % user_id,
            limit=1, output_fields=["memory_id"],
            search_params={"metric_type": self._milvus_config.dense_metric_type},
        )
        if similar and similar[0]:
            top = similar[0][0]
            score = float(top.get("distance", 0.0) if isinstance(top, Mapping) else getattr(top, "distance", 0.0))
            if score >= self._config.duplicate_score:
                return False
        row = {
            "memory_id": str(uuid.uuid4()), "user_id": user_id, "memory_type": memory_type,
            "content": content, "content_sha256": content_sha256, "importance": float(importance),
            "source_conversation_id": conversation_id[:64], "source_request_id": request_id[:64],
            "created_at_epoch": int(time.time()), "active": True, "dense_vector": vector,
        }
        self._client.insert(collection_name=self._config.collection, data=[row])
        return True

    # 调用现有 BGE-M3 生成单条 Dense 向量，并在进入 Milvus 前校验维度和数值。
    def _dense_vector(self, text: str) -> list[float]:
        embedded = self._embedding.embed_documents([text])
        if len(embedded.dense) != 1 or len(embedded.dense[0]) != self._dimensions:
            raise ValueError("语义记忆向量维度或数量不匹配")
        vector = [float(value) for value in embedded.dense[0]]
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("语义记忆向量包含无效数值")
        return vector
