"""MySQL 父子块和索引任务持久化。"""

import json
import re
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, Generator, List, Optional, Sequence, Tuple

import pymysql

from ..domain import ChildChunk, DocumentIndexEvent, DocumentIndexTask, ParentChunk


PENDING = 0
PROCESSING = 1
RETRY_WAIT = 2
COMPLETED = 3
FAILED_PERMANENT = 4


# 将 Go MySQL DSN 转成 PyMySQL 连接参数，保持现有配置可直接复用。
def parse_mysql_dsn(dsn: str) -> Dict[str, Any]:
    match = re.fullmatch(r"([^:]+):([^@]*)@tcp\(([^:]+):(\d+)\)/([^?]+)(?:\?(.*))?", dsn)
    if not match:
        raise ValueError("database.dsn 必须使用 Go MySQL DSN 格式")
    return {
        "user": match.group(1),
        "password": match.group(2),
        "host": match.group(3),
        "port": int(match.group(4)),
        "database": match.group(5),
        "charset": "utf8mb4",
        "autocommit": False,
        "cursorclass": pymysql.cursors.DictCursor,
    }


class MySQLRepository:
    """复用 Go Agent 的任务表，并保存父块、子块及映射关系。"""

    # 保存连接参数，每次操作创建短生命周期连接以支持多线程 Consumer。
    def __init__(self, dsn: str) -> None:
        self._params = parse_mysql_dsn(dsn)

    # 创建启用提交或回滚边界的数据库连接。
    @contextmanager
    def _connection(self) -> Generator[Any, None, None]:
        connection = pymysql.connect(**self._params)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # 使用文档版本幂等键记录 RocketMQ INDEX 事件。
    def record_index_event(self, event: DocumentIndexEvent) -> bool:
        sql = """INSERT IGNORE INTO agent_document_index_task
        (event_id, document_id, index_version, user_id, knowledge_base_id, status, received_at, next_retry_at)
        VALUES (%s, %s, %s, %s, %s, 0, UTC_TIMESTAMP(), UTC_TIMESTAMP())"""
        with self._connection() as connection:
            with connection.cursor() as cursor:
                return cursor.execute(sql, (event.event_id, event.document_id, event.index_version, event.user_id, event.knowledge_base_id)) == 1

    # 使用 FOR UPDATE SKIP LOCKED 原子领取任务并回收超时锁。
    def claim_task(self, worker_id: str, lock_timeout: float) -> Optional[DocumentIndexTask]:
        stale_at = datetime.utcnow() - timedelta(seconds=lock_timeout)
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM agent_document_index_task
                    WHERE ((status IN (0, 2) AND next_retry_at <= UTC_TIMESTAMP())
                    OR (status = 1 AND locked_at < %s)) ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED""",
                    (stale_at,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                cursor.execute(
                    """UPDATE agent_document_index_task SET status=1, attempts=attempts+1,
                    locked_by=%s, locked_at=UTC_TIMESTAMP(), last_error=NULL,
                    started_at=COALESCE(started_at, UTC_TIMESTAMP()) WHERE id=%s""",
                    (worker_id, row["id"]),
                )
                return DocumentIndexTask(
                    int(row["id"]), str(row["event_id"]), int(row["document_id"]), int(row["index_version"]),
                    int(row["user_id"]), int(row["knowledge_base_id"]), int(row["attempts"]) + 1,
                    row.get("failure_code"), row.get("failure_message"),
                )

    # 在一个 MySQL 事务中幂等替换当前版本全部父块和子块。
    def replace_chunks(self, document_id: int, index_version: int, parents: Sequence[ParentChunk], children: Sequence[ChildChunk]) -> None:
        if not parents or not children:
            raise ValueError("父块和子块不能为空")
        sql = """INSERT INTO agent_document_chunk
        (id, document_id, knowledge_base_id, user_id, index_version, chunk_type, parent_id,
         chunk_index, content, content_sha256, metadata, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP())"""
        rows: List[Tuple[Any, ...]] = []
        for chunk in parents:
            rows.append((chunk.id, chunk.document_id, chunk.knowledge_base_id, chunk.user_id, chunk.index_version, 0, None, chunk.index, chunk.content, chunk.content_sha256, json.dumps(chunk.metadata, ensure_ascii=False)))
        for chunk in children:
            rows.append((chunk.id, chunk.document_id, chunk.knowledge_base_id, chunk.user_id, chunk.index_version, 1, chunk.parent_id, chunk.index, chunk.content, chunk.content_sha256, json.dumps(chunk.metadata, ensure_ascii=False)))
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM agent_document_chunk WHERE document_id=%s AND index_version=%s", (document_id, index_version))
                cursor.executemany(sql, rows)

    # 删除索引失败版本的父子块，供跨存储补偿使用。
    def delete_chunks(self, document_id: int, index_version: int) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM agent_document_chunk WHERE document_id=%s AND index_version=%s", (document_id, index_version))

    # 将当前持锁任务标记为完成。
    def mark_completed(self, task_id: int, worker_id: str) -> None:
        self._update_locked(task_id, worker_id, "status=3, completed_at=UTC_TIMESTAMP(), locked_by=NULL, locked_at=NULL, last_error=NULL", ())

    # 记录可重试错误并释放任务锁。
    def mark_retry(self, task_id: int, worker_id: str, next_retry_at: datetime, error: str) -> None:
        self._update_locked(task_id, worker_id, "status=2, next_retry_at=%s, last_error=%s, locked_by=NULL, locked_at=NULL", (next_retry_at, error))

    # 保存永久失败结论，后续仅重试 Logic 失败回调。
    def mark_failure_report_pending(self, task_id: int, worker_id: str, next_retry_at: datetime, code: str, message: str, error: str) -> None:
        self._update_locked(task_id, worker_id, "status=2, next_retry_at=%s, failure_code=%s, failure_message=%s, last_error=%s, locked_by=NULL, locked_at=NULL", (next_retry_at, code, message, error))

    # 将已经成功上报 Logic 的任务置为永久失败终态。
    def mark_failed_permanent(self, task_id: int, worker_id: str, error: str) -> None:
        self._update_locked(task_id, worker_id, "status=4, completed_at=UTC_TIMESTAMP(), last_error=%s, locked_by=NULL, locked_at=NULL", (error,))

    # 所有状态更新都校验 Worker 所有权，防止过期 Worker 覆盖新任务状态。
    def _update_locked(self, task_id: int, worker_id: str, assignments: str, values: Tuple[Any, ...]) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                affected = cursor.execute("UPDATE agent_document_index_task SET %s WHERE id=%%s AND status=1 AND locked_by=%%s" % assignments, values + (task_id, worker_id))
                if affected != 1:
                    raise RuntimeError("文档索引任务执行锁已丢失")
