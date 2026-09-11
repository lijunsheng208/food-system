"""文档解析、切片和索引任务使用的领域模型。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SourceDocument:
    """描述从 Logic 下载的原始文档及其业务归属。"""

    document_id: int
    knowledge_base_id: int
    user_id: int
    index_version: int
    filename: str
    extension: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class DocumentBlock:
    """描述 Unstructured 解析得到的文档元素及其树关系。"""

    block_type: str
    text: str
    order: int
    heading_level: Optional[int] = None
    heading_path: Tuple[str, ...] = ()
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    element_id: str = ""
    parent_id: str = ""


@dataclass(frozen=True)
class ParsedDocument:
    """保存格式无关的结构化文档和解析元数据。"""

    title: str
    blocks: List[DocumentBlock]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParentChunk:
    """表示生成阶段使用的章节或页面窗口。"""

    id: str
    document_id: int
    knowledge_base_id: int
    user_id: int
    index_version: int
    index: int
    content: str
    content_sha256: str
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class ChildChunk:
    """表示用于 Embedding 和 BM25 检索的小文本块。"""

    id: str
    parent_id: str
    document_id: int
    knowledge_base_id: int
    user_id: int
    index_version: int
    index: int
    content: str
    content_sha256: str
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class DocumentIndexEvent:
    """对应 Logic Transactional Outbox 发布的 INDEX 事件。"""

    schema_version: int
    event_id: str
    event_type: str
    document_id: int
    user_id: int
    knowledge_base_id: int
    index_version: int
    occurred_at: datetime


@dataclass(frozen=True)
class DocumentIndexTask:
    """表示从 Agent MySQL 领取的一次索引任务。"""

    id: int
    event_id: str
    document_id: int
    index_version: int
    user_id: int
    knowledge_base_id: int
    attempts: int
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None


@dataclass(frozen=True)
class DownloadTicket:
    """保存 Logic 签发的短期 OSS 下载信息。"""

    download_url: str
    original_filename: str
    file_extension: str
    content_type: str
    file_size: int
    sha256: str
    expires_at: datetime


class PermanentDocumentError(Exception):
    """表示重试无法恢复的文档格式、内容或配置错误。"""

    # 初始化可安全回传给 Logic 的稳定错误信息。
    def __init__(self, code: str, public_message: str, detail: str = "") -> None:
        super().__init__(detail or public_message)
        self.code = code
        self.public_message = public_message
