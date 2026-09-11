"""文档索引编排和可靠任务 Worker。"""

import logging
import re
import socket
import threading
from datetime import datetime, timedelta
from typing import Optional

from .chunking import ParentChildChunker
from .clients import DocumentDownloader, EmbeddingClient, LogicClient, OpenSearchRepository
from .config import WorkerConfig
from .domain import DocumentIndexTask, PermanentDocumentError, SourceDocument
from .parsing import ParserRegistry
from .repositories import MySQLRepository, VectorRepository


logger = logging.getLogger(__name__)


class DocumentIndexer:
    """执行下载、结构化解析、父子切片和三套索引写入。"""

    # 注入索引流程依赖，使解析和存储可以独立测试。
    def __init__(
        self,
        mysql: MySQLRepository,
        vectors: VectorRepository,
        opensearch: Optional[OpenSearchRepository],
        logic: LogicClient,
        downloader: DocumentDownloader,
        embeddings: EmbeddingClient,
        parsers: ParserRegistry,
        chunker: ParentChildChunker,
    ) -> None:
        self._mysql = mysql
        self._vectors = vectors
        self._opensearch = opensearch
        self._logic = logic
        self._downloader = downloader
        self._embeddings = embeddings
        self._parsers = parsers
        self._chunker = chunker

    # 处理一个文档版本；只有父子块、向量和 BM25 都成功才允许回调完成。
    def process(self, task: DocumentIndexTask) -> None:
        ticket = self._logic.get_download_ticket(task.document_id, task.index_version)
        content = self._downloader.download(ticket)
        source = SourceDocument(
            task.document_id, task.knowledge_base_id, task.user_id, task.index_version,
            ticket.original_filename, ticket.file_extension, ticket.content_type, content,
        )
        parser = self._parsers.resolve(source.extension, source.filename)
        parsed = parser.parse(source)
        parents, children = self._chunker.chunk(source, parsed)
        if not parents or not children:
            raise PermanentDocumentError("DOCUMENT_EMPTY", "文档解析结果为空")
        vectors = self._embeddings.embed_documents([chunk.content for chunk in children])
        self._mysql.replace_chunks(task.document_id, task.index_version, parents, children)
        try:
            self._vectors.replace_version(task.document_id, task.index_version, children, vectors)
            if self._opensearch is not None:
                self._opensearch.replace_version(task.document_id, task.index_version, children)
        except Exception:
            self._compensate(task)
            raise

    # 尽力清理未完整写入的跨存储版本，原始异常仍由调用方处理。
    def _compensate(self, task: DocumentIndexTask) -> None:
        if self._opensearch is not None:
            try:
                self._opensearch.delete_version(task.document_id, task.index_version)
            except Exception as exc:
                logger.error("清理 OpenSearch 失败: document_id=%d error=%s", task.document_id, sanitize_error(exc))
        try:
            self._vectors.delete_version(task.document_id, task.index_version)
        except Exception as exc:
            logger.error("清理 pgvector 失败: document_id=%d error=%s", task.document_id, sanitize_error(exc))
        try:
            self._mysql.delete_chunks(task.document_id, task.index_version)
        except Exception as exc:
            logger.error("清理 MySQL 父子块失败: document_id=%d error=%s", task.document_id, sanitize_error(exc))


class DocumentWorker:
    """可靠领取任务、指数退避，并向 Logic 回调最终状态。"""

    # 使用主机名和线程 ID 构造 Worker 锁所有者标识。
    def __init__(self, repository: MySQLRepository, logic: LogicClient, indexer: DocumentIndexer, config: WorkerConfig) -> None:
        self._repository = repository
        self._logic = logic
        self._indexer = indexer
        self._config = config
        self._worker_id = "%s-python-%d" % (socket.gethostname(), threading.get_ident())

    # 持续处理所有到期任务，直到收到停止事件。
    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            processed = self.process_one()
            if not processed:
                stop.wait(self._config.poll_interval)

    # 领取并处理单个任务，返回当前轮询是否取得任务。
    def process_one(self) -> bool:
        try:
            task = self._repository.claim_task(self._worker_id, self._config.lock_timeout)
        except Exception as exc:
            logger.error("领取文档索引任务失败: %s", sanitize_error(exc))
            return False
        if task is None:
            return False
        if task.failure_code and task.failure_message:
            self._report_permanent_failure(task, task.failure_code, task.failure_message, RuntimeError("等待上报永久失败"))
            return True
        try:
            self._indexer.process(task)
            self._logic.complete_index(task.document_id, task.index_version)
            self._repository.mark_completed(task.id, self._worker_id)
        except Exception as exc:
            permanent = isinstance(exc, PermanentDocumentError) or task.attempts >= self._config.max_attempts
            if permanent:
                code = exc.code if isinstance(exc, PermanentDocumentError) else "DOCUMENT_INDEX_RETRY_EXHAUSTED"
                message = exc.public_message if isinstance(exc, PermanentDocumentError) else "文档索引重试次数已耗尽"
                self._report_permanent_failure(task, code, message, exc)
            else:
                next_retry = datetime.utcnow() + timedelta(seconds=self._retry_delay(task.attempts))
                self._repository.mark_retry(task.id, self._worker_id, next_retry, sanitize_error(exc))
        return True

    # 上报永久失败；回调失败时只重试回调，不再重复解析和向量化。
    def _report_permanent_failure(self, task: DocumentIndexTask, code: str, message: str, cause: Exception) -> None:
        try:
            self._logic.fail_index(task.document_id, task.index_version, code, message)
        except Exception as exc:
            next_retry = datetime.utcnow() + timedelta(seconds=self._retry_delay(task.attempts))
            self._repository.mark_failure_report_pending(task.id, self._worker_id, next_retry, code, message, sanitize_error(exc))
            return
        self._repository.mark_failed_permanent(task.id, self._worker_id, sanitize_error(cause))

    # 根据已领取次数计算有上限的指数退避秒数。
    def _retry_delay(self, attempts: int) -> float:
        return min(self._config.retry_base * (2 ** min(max(attempts - 1, 0), 16)), self._config.retry_max)


# 清理错误中的签名 URL、Bearer Token 和超长上下文，防止敏感信息入库。
def sanitize_error(error: Exception) -> str:
    value = str(error)
    value = re.sub(r"(?i)bearer\s+[a-z0-9._~+\-/]+=*", "Bearer [REDACTED]", value)
    value = re.sub(r"https?://\S+", "[URL_REDACTED]", value)
    return value[:500]
