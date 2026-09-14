"""基于 Milvus 原生 Hybrid Search 的权限隔离和父子两阶段检索实现。"""

import json
from dataclasses import replace
from typing import Any, Dict, List, Sequence

from pymilvus import AnnSearchRequest, RRFRanker

from .interfaces import ChunkReranker, EmbeddedChunks, HybridRetriever, RetrievalQuery, RetrievedChunk


class MilvusHybridRetriever:
    """使用同一 Collection 执行 Dense、Sparse 检索并以 RRF 融合结果。"""

    # 初始化检索器；embedding_client 只需实现 embed_documents(texts) 方法。
    def __init__(self, client: Any, collection: str, embedding_client: Any, dimensions: int, rrf_k: int = 60, candidate_limit: int = 50) -> None:
        if not collection or dimensions <= 0 or rrf_k <= 0 or candidate_limit <= 0:
            raise ValueError("Milvus 检索配置无效")
        self._client, self._collection, self._embedding, self._dimensions = client, collection, embedding_client, dimensions
        self._rrf_k, self._candidate_limit = rrf_k, candidate_limit

    # retrieve 校验权限过滤条件，分别召回 Dense/Sparse 候选后返回融合结果。
    def retrieve(self, query: RetrievalQuery) -> Sequence[RetrievedChunk]:
        if not query.text.strip() or query.top_k <= 0 or query.knowledge_base_id <= 0 or query.user_id <= 0:
            raise ValueError("检索请求参数无效")
        embedded: EmbeddedChunks = self._embedding.embed_documents([query.text])
        if len(embedded.dense) != 1 or len(embedded.sparse) != 1 or len(embedded.dense[0]) != self._dimensions:
            raise ValueError("查询向量维度或数量不匹配")
        expr = self._filter(query)
        # 每路候选数与旧评估保持一致，再由 Milvus 原生 RRFRanker 统一融合并截取最终 TopK。
        candidate_limit = max(query.top_k, self._candidate_limit)
        requests = [
            AnnSearchRequest([list(embedded.dense[0])], "dense_vector", {"metric_type": "COSINE"}, candidate_limit, expr=expr),
            AnnSearchRequest([dict(embedded.sparse[0])], "sparse_vector", {"metric_type": "IP"}, candidate_limit, expr=expr),
        ]
        results = self._client.hybrid_search(
            self._collection,
            requests,
            RRFRanker(self._rrf_k),
            limit=query.top_k,
            output_fields=["*"],
        )
        rows = results[0] if results else []
        return [self._to_chunk(row) for row in rows]

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

    # _to_chunk 兼容不同 pymilvus 版本的 entity 包装，并转换为线上统一文档块。
    @staticmethod
    def _to_chunk(row: Any) -> RetrievedChunk:
        item: Dict[str, Any] = row.get("entity", row) if isinstance(row, dict) else getattr(row, "entity", {})
        item = dict(item or {})
        score = float(row.get("distance", 0.0) if isinstance(row, dict) else getattr(row, "distance", 0.0))
        return RetrievedChunk(str(item["chunk_id"]), int(item["document_id"]), int(item["knowledge_base_id"]), int(item.get("index_version", 0)), str(item.get("parent_id", "")), str(item.get("content", "")), score, dict(item.get("metadata") or {}))


class MilvusParentChildRetriever:
    """先召回 Child，再扩展同 Parent 的 Child 并使用 Cross-Encoder 重排。"""

    # 初始化两阶段检索器；recall_top_k 限定为 20～50，控制父块扩展的时延和候选规模。
    def __init__(self, base: HybridRetriever, client: Any, collection: str, reranker: ChunkReranker, recall_top_k: int = 50) -> None:
        if not collection or not 20 <= recall_top_k <= 50:
            raise ValueError("父子检索 recall_top_k 必须在 20 到 50 之间")
        self._base = base
        self._client = client
        self._collection = collection
        self._reranker = reranker
        self._recall_top_k = recall_top_k

    # retrieve 执行 Child 初召回、Parent 扩展、候选去重和最终 Child TopK 重排。
    def retrieve(self, query: RetrievalQuery) -> Sequence[RetrievedChunk]:
        if not query.text.strip() or query.top_k <= 0:
            raise ValueError("检索请求参数无效")
        recalled = list(self._base.retrieve(replace(query, top_k=self._recall_top_k)))
        if not recalled:
            return []
        parent_ids = list(dict.fromkeys(chunk.parent_id for chunk in recalled if chunk.parent_id))
        expanded = self._query_children(query, parent_ids) if parent_ids else []
        # 初召回结果也进入候选集，使缺少 parent_id 或并发索引切换时仍可完成重排。
        candidates = self._deduplicate([*recalled, *expanded])
        scores = self._reranker.score(query.text, [chunk.content for chunk in candidates])
        reranked = [replace(chunk, score=float(score)) for chunk, score in zip(candidates, scores)]
        reranked.sort(key=lambda chunk: (-chunk.score, chunk.chunk_id))
        return reranked[: query.top_k]

    # _query_children 在原请求的租户、知识库、版本和文档范围内查询相关 Parent 的全部 Child。
    def _query_children(self, query: RetrievalQuery, parent_ids: Sequence[str]) -> List[RetrievedChunk]:
        parent_values = ", ".join(json.dumps(value, ensure_ascii=False) for value in parent_ids)
        expression = "%s and parent_id in [%s]" % (MilvusHybridRetriever._filter(query), parent_values)
        rows = self._client.query(
            collection_name=self._collection,
            filter=expression,
            output_fields=["chunk_id", "document_id", "knowledge_base_id", "index_version", "parent_id", "content", "metadata"],
        )
        return [MilvusHybridRetriever._to_chunk(row) for row in rows]

    # _deduplicate 按规范 chunk_id 去重，并优先保留带初召回分数的同一 Child。
    @staticmethod
    def _deduplicate(chunks: Sequence[RetrievedChunk]) -> List[RetrievedChunk]:
        unique: Dict[str, RetrievedChunk] = {}
        for chunk in chunks:
            unique.setdefault(chunk.chunk_id, chunk)
        return list(unique.values())
