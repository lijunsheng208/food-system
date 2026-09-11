"""基于 Milvus Dense/Sparse 向量的权限隔离检索实现。"""

from typing import Any, Dict, Iterable, List, Sequence

from .interfaces import EmbeddedChunks, RetrievalQuery, RetrievedChunk


class MilvusHybridRetriever:
    """使用同一 Collection 执行 Dense、Sparse 检索并以 RRF 融合结果。"""

    # 初始化检索器；embedding_client 只需实现 embed_documents(texts) 方法。
    def __init__(self, client: Any, collection: str, embedding_client: Any, dimensions: int, rrf_k: int = 60) -> None:
        if not collection or dimensions <= 0 or rrf_k <= 0:
            raise ValueError("Milvus 检索配置无效")
        self._client, self._collection, self._embedding, self._dimensions, self._rrf_k = client, collection, embedding_client, dimensions, rrf_k

    # retrieve 校验权限过滤条件，分别召回 Dense/Sparse 候选后返回融合结果。
    def retrieve(self, query: RetrievalQuery) -> Sequence[RetrievedChunk]:
        if not query.text.strip() or query.top_k <= 0 or query.knowledge_base_id <= 0 or query.user_id <= 0:
            raise ValueError("检索请求参数无效")
        embedded: EmbeddedChunks = self._embedding.embed_documents([query.text])
        if len(embedded.dense) != 1 or len(embedded.sparse) != 1 or len(embedded.dense[0]) != self._dimensions:
            raise ValueError("查询向量维度或数量不匹配")
        expr = self._filter(query)
        dense = self._search("dense_vector", list(embedded.dense[0]), expr, query.top_k)
        sparse = self._search("sparse_vector", dict(embedded.sparse[0]), expr, query.top_k)
        return self._fuse(dense, sparse, query.top_k)

    # _filter 固化用户、知识库、活动版本和可选文档范围，防止跨租户召回。
    @staticmethod
    def _filter(query: RetrievalQuery) -> str:
        parts = ["user_id == %d" % query.user_id, "knowledge_base_id == %d" % query.knowledge_base_id, "active == true"]
        if query.index_version > 0:
            parts.append("index_version == %d" % query.index_version)
        if query.document_ids:
            ids = ", ".join(str(int(value)) for value in query.document_ids)
            parts.append("document_id in [%s]" % ids)
        return " and ".join(parts)

    # _search 兼容 MilvusClient 返回字典行和对象行两种 SDK 结果格式。
    def _search(self, field: str, vector: Any, expr: str, limit: int) -> List[Dict[str, Any]]:
        results = self._client.search(collection_name=self._collection, data=[vector], anns_field=field, limit=limit, filter=expr, output_fields=["*"])
        rows = results[0] if results else []
        normalized = []
        for row in rows:
            item = row if isinstance(row, dict) else getattr(row, "entity", {})
            item = dict(item or {})
            item["_score"] = float(row.get("distance", 0.0) if isinstance(row, dict) else getattr(row, "distance", 0.0))
            normalized.append(item)
        return normalized

    # _fuse 使用 Reciprocal Rank Fusion，避免不同向量度量的分数不可直接比较。
    def _fuse(self, dense: Iterable[Dict[str, Any]], sparse: Iterable[Dict[str, Any]], top_k: int) -> List[RetrievedChunk]:
        merged: Dict[str, Dict[str, Any]] = {}
        for rows in (dense, sparse):
            for rank, row in enumerate(rows):
                chunk_id = str(row.get("chunk_id", ""))
                if not chunk_id:
                    continue
                entry = merged.setdefault(chunk_id, {"row": row, "score": 0.0})
                entry["score"] += 1.0 / (self._rrf_k + rank + 1)
        ordered = sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:top_k]
        return [RetrievedChunk(str(item["row"]["chunk_id"]), int(item["row"]["document_id"]), int(item["row"]["knowledge_base_id"]), int(item["row"].get("index_version", 0)), str(item["row"].get("parent_id", "")), str(item["row"].get("content", "")), float(item["score"]), dict(item["row"].get("metadata") or {})) for item in ordered]
