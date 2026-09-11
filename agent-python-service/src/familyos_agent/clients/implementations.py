"""Logic、Embedding 和 OpenSearch 外部服务客户端。"""

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence
from urllib.parse import urlparse

import grpc
import httpx

from ..config import EmbeddingConfig, LogicConfig, OpenSearchConfig
from ..domain import ChildChunk, DownloadTicket, PermanentDocumentError
from ..generated.knowledge.v1 import knowledge_pb2
from ..transport.contracts import (
    COMPLETE_DOCUMENT_INDEX_METHOD,
    FAIL_DOCUMENT_INDEX_METHOD,
    GET_DOCUMENT_DOWNLOAD_TICKET_METHOD,
    INTERNAL_TOKEN_HEADER,
)


class LogicClient:
    """调用现有 Logic KnowledgeInternalService gRPC 接口。"""

    # 创建与 Go 服务相同的明文内网 gRPC Channel 和三个 Unary RPC。
    def __init__(self, config: LogicConfig) -> None:
        self._channel = grpc.insecure_channel(config.target)
        self._token = config.agent_token
        self._timeout = config.request_timeout
        self._get_ticket = self._channel.unary_unary(
            GET_DOCUMENT_DOWNLOAD_TICKET_METHOD,
            request_serializer=knowledge_pb2.GetDocumentDownloadTicketRequest.SerializeToString,
            response_deserializer=knowledge_pb2.GetDocumentDownloadTicketResponse.FromString,
        )
        self._complete = self._channel.unary_unary(
            COMPLETE_DOCUMENT_INDEX_METHOD,
            request_serializer=knowledge_pb2.CompleteDocumentIndexRequest.SerializeToString,
            response_deserializer=knowledge_pb2.CompleteDocumentIndexResponse.FromString,
        )
        self._fail = self._channel.unary_unary(
            FAIL_DOCUMENT_INDEX_METHOD,
            request_serializer=knowledge_pb2.FailDocumentIndexRequest.SerializeToString,
            response_deserializer=knowledge_pb2.FailDocumentIndexResponse.FromString,
        )

    # 请求与任务文档和索引版本严格一致的短期 OSS 下载票据。
    def get_download_ticket(self, document_id: int, index_version: int) -> DownloadTicket:
        response = self._get_ticket(
            knowledge_pb2.GetDocumentDownloadTicketRequest(document_id=document_id, index_version=index_version),
            timeout=self._timeout,
            metadata=((INTERNAL_TOKEN_HEADER, self._token),),
        )
        if response.code != 0:
            raise RuntimeError("Logic 拒绝签发文档下载票据: code=%d message=%s" % (response.code, response.message))
        expires_at = _parse_rfc3339(response.expires_at)
        if response.document_id != document_id or response.index_version != index_version or not response.download_url or response.file_size <= 0 or expires_at <= datetime.now(timezone.utc):
            raise RuntimeError("Logic 下载票据响应无效")
        return DownloadTicket(response.download_url, response.original_filename, response.file_extension, response.content_type, response.file_size, response.sha256, expires_at)

    # 通知 Logic 激活已经完整写入的索引版本。
    def complete_index(self, document_id: int, index_version: int) -> None:
        response = self._complete(
            knowledge_pb2.CompleteDocumentIndexRequest(document_id=document_id, index_version=index_version),
            timeout=self._timeout,
            metadata=((INTERNAL_TOKEN_HEADER, self._token),),
        )
        if response.code != 0:
            raise RuntimeError("Logic 拒绝激活索引版本: code=%d message=%s" % (response.code, response.message))

    # 通知 Logic 将不可恢复的索引版本标记为失败。
    def fail_index(self, document_id: int, index_version: int, code: str, message: str) -> None:
        response = self._fail(
            knowledge_pb2.FailDocumentIndexRequest(document_id=document_id, index_version=index_version, failure_code=code, failure_message=message),
            timeout=self._timeout,
            metadata=((INTERNAL_TOKEN_HEADER, self._token),),
        )
        if response.code != 0:
            raise RuntimeError("Logic 拒绝记录索引失败: code=%d message=%s" % (response.code, response.message))

    # 关闭底层 gRPC Channel。
    def close(self) -> None:
        self._channel.close()


# 解析 Logic 返回的 RFC3339 时间并统一为 UTC aware datetime。
def _parse_rfc3339(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class DocumentDownloader:
    """下载 OSS 文件并验证协议、大小和 SHA256。"""

    # 保存文件大小限制和网络超时。
    def __init__(self, max_file_size: int, timeout: float) -> None:
        self._max_file_size = max_file_size
        self._client = httpx.Client(timeout=timeout, follow_redirects=False)

    # 只允许 HTTP(S) 票据，并在解析前完成完整性校验。
    def download(self, ticket: DownloadTicket) -> bytes:
        parsed = urlparse(ticket.download_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise PermanentDocumentError("DOCUMENT_TICKET_INVALID", "文档下载票据无效")
        if ticket.file_size <= 0 or ticket.file_size > self._max_file_size:
            raise PermanentDocumentError("DOCUMENT_TOO_LARGE", "文档大小超出索引限制")
        with self._client.stream("GET", ticket.download_url) as response:
            response.raise_for_status()
            parts: List[bytes] = []
            size = 0
            for part in response.iter_bytes():
                size += len(part)
                if size > self._max_file_size:
                    raise PermanentDocumentError("DOCUMENT_TOO_LARGE", "文档大小超出索引限制")
                parts.append(part)
        content = b"".join(parts)
        if len(content) != ticket.file_size:
            raise PermanentDocumentError("DOCUMENT_SIZE_MISMATCH", "下载文档大小与上传记录不匹配")
        if ticket.sha256 and hashlib.sha256(content).hexdigest().lower() != ticket.sha256.lower():
            raise PermanentDocumentError("DOCUMENT_HASH_MISMATCH", "文档完整性校验失败")
        return content

    # 关闭 HTTP 连接池。
    def close(self) -> None:
        self._client.close()


class EmbeddingClient:
    """批量调用现有 OpenAI-compatible Embedding 接口。"""

    # 保存模型、维度和批大小等兼容配置。
    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._client = httpx.Client(timeout=config.timeout)

    # 按配置批量向量化子块，并恢复为原始输入顺序。
    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        result: List[List[float]] = []
        endpoint = self._config.base_url.rstrip("/") + "/embeddings"
        for start in range(0, len(texts), self._config.batch_size):
            batch = list(texts[start : start + self._config.batch_size])
            response = self._client.post(endpoint, headers={"Authorization": "Bearer " + self._config.api_key}, json={"model": self._config.model, "input": batch})
            response.raise_for_status()
            payload = response.json()
            items = sorted(payload.get("data", []), key=lambda item: item.get("index", -1))
            if len(items) != len(batch):
                raise PermanentDocumentError("EMBEDDING_INCOMPATIBLE", "Embedding 返回数量与子块数量不匹配")
            for item in items:
                vector = item.get("embedding")
                if not isinstance(vector, list) or len(vector) != self._config.dimensions or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector):
                    raise PermanentDocumentError("EMBEDDING_INCOMPATIBLE", "Embedding 维度或返回结构与配置不匹配")
                result.append([float(value) for value in vector])
        return result

    # 关闭 Embedding HTTP 连接池。
    def close(self) -> None:
        self._client.close()


class OpenSearchRepository:
    """在 OpenSearch 中只索引可检索子块和父块引用元数据。"""

    # 初始化 HTTP 客户端并确保索引映射包含父子字段。
    def __init__(self, config: OpenSearchConfig) -> None:
        self._config = config
        auth = (config.username, config.password) if config.username else None
        self._client = httpx.Client(base_url=config.endpoint.rstrip("/"), timeout=config.timeout, auth=auth)
        self._ensure_index()

    # 创建新索引，并对已存在索引补充父子映射字段。
    def _ensure_index(self) -> None:
        mapping = {
            "settings": {"index": {"similarity": {"default": {"type": "BM25", "k1": 1.2, "b": 0.75}}, "analysis": {"analyzer": {"familyos_index": {"type": "custom", "tokenizer": "ik_max_word", "filter": ["lowercase"]}, "familyos_search": {"type": "custom", "tokenizer": "ik_smart", "filter": ["lowercase"]}}}}},
            "mappings": {"properties": self._properties()},
        }
        response = self._client.put("/" + self._config.index, json=mapping)
        if response.status_code not in (200, 201, 400):
            response.raise_for_status()
        if response.status_code == 400:
            update = self._client.put("/%s/_mapping" % self._config.index, json={"properties": self._properties()})
            update.raise_for_status()

    # 返回子块检索所需的显式字段类型。
    def _properties(self) -> Dict[str, Any]:
        return {
            "chunk_id": {"type": "keyword"}, "parent_id": {"type": "keyword"},
            "document_id": {"type": "long"}, "knowledge_base_id": {"type": "long"},
            "user_id": {"type": "long"}, "index_version": {"type": "integer"},
            "active": {"type": "boolean"}, "filename": {"type": "keyword"},
            "heading_path": {"type": "keyword"},
            "content": {"type": "text", "analyzer": "familyos_index", "search_analyzer": "familyos_search"},
            "content_sha256": {"type": "keyword"},
        }

    # 幂等替换一个文档版本的子块，并停用该文档旧版本。
    def replace_version(self, document_id: int, index_version: int, chunks: Sequence[ChildChunk]) -> None:
        self.delete_version(document_id, index_version)
        lines: List[str] = []
        for chunk in chunks:
            lines.append(json.dumps({"index": {"_index": self._config.index, "_id": chunk.id}}, separators=(",", ":")))
            lines.append(json.dumps({
                "chunk_id": chunk.id, "parent_id": chunk.parent_id, "document_id": chunk.document_id,
                "knowledge_base_id": chunk.knowledge_base_id, "user_id": chunk.user_id,
                "index_version": chunk.index_version, "active": True,
                "filename": chunk.metadata.get("filename", ""), "heading_path": chunk.metadata.get("heading_path", []),
                "content": chunk.content, "content_sha256": chunk.content_sha256,
            }, ensure_ascii=False, separators=(",", ":")))
        response = self._client.post("/_bulk", content=("\n".join(lines) + "\n").encode("utf-8"), headers={"Content-Type": "application/x-ndjson"})
        response.raise_for_status()
        if response.json().get("errors"):
            raise RuntimeError("OpenSearch Bulk 部分子块写入失败")
        query = {"script": {"source": "ctx._source.active = false"}, "query": {"bool": {"filter": [{"term": {"document_id": document_id}}, {"bool": {"must_not": {"term": {"index_version": index_version}}}}]}}}
        deactivate = self._client.post("/%s/_update_by_query?conflicts=proceed" % self._config.index, json=query)
        deactivate.raise_for_status()

    # 删除指定文档版本的 BM25 子块。
    def delete_version(self, document_id: int, index_version: int) -> None:
        query = {"query": {"bool": {"filter": [{"term": {"document_id": document_id}}, {"term": {"index_version": index_version}}]}}}
        response = self._client.post("/%s/_delete_by_query?conflicts=proceed" % self._config.index, json=query)
        if response.status_code != 404:
            response.raise_for_status()

    # 关闭 OpenSearch HTTP 连接池。
    def close(self) -> None:
        self._client.close()
