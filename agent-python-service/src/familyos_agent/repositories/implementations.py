"""MySQL 父子块和索引任务持久化。"""

import json
import re
import uuid
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

    # 创建绑定用户和知识库的会话，供 Chat gRPC 创建会话 RPC 使用。
    def create_conversation(self, user_id: int, knowledge_base_id: int) -> str:
        conversation_id = str(uuid.uuid4())
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO agent_conversation (id,user_id,knowledge_base_id) VALUES (%s,%s,%s)", (conversation_id, user_id, knowledge_base_id))
        return conversation_id

    # 记录一次 Chat 用户消息和生成中的助手消息，依赖 request_id 唯一约束实现幂等。
    def begin_chat(self, request: Any) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT user_id,knowledge_base_id FROM agent_conversation WHERE id=%s FOR UPDATE", (request.conversation_id,))
                row = cursor.fetchone()
                if not row or int(row["user_id"]) != request.user_id or int(row["knowledge_base_id"]) != request.knowledge_base_id:
                    raise ValueError("会话不存在或无权访问")
                cursor.execute("INSERT IGNORE INTO agent_conversation_message (id,conversation_id,request_id,role,status,content) VALUES (%s,%s,%s,1,2,%s)", (str(uuid.uuid4()), request.conversation_id, request.request_id, request.message))
                cursor.execute("INSERT IGNORE INTO agent_conversation_message (id,conversation_id,request_id,role,status,content) VALUES (%s,%s,%s,2,1,'')", (str(uuid.uuid4()), request.conversation_id, request.request_id))

    # 读取请求终态，重复 request_id 直接复用已保存结果，避免重复调用模型。
    def get_chat_result(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status,content,citations,error_code,error_message FROM agent_conversation_message WHERE request_id=%s AND role=2 LIMIT 1", (request_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return {"status": int(row["status"]), "content": row.get("content", ""), "citations": json.loads(row.get("citations") or "[]"), "error_code": row.get("error_code", ""), "error_message": row.get("error_message", "")}

    # 读取已完成的会话原文和滚动摘要，排除当前请求避免重复注入用户消息。
    def get_chat_context(self, conversation_id: str, exclude_request_id: str) -> Dict[str, Any]:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT summary,through_created_at,through_message_id FROM agent_conversation_memory WHERE conversation_id=%s", (conversation_id,))
                memory = cursor.fetchone()
                sql = """SELECT id,role,content,created_at FROM agent_conversation_message
                    WHERE conversation_id=%s AND request_id<>%s AND status=2"""
                params: Tuple[Any, ...] = (conversation_id, exclude_request_id)
                if memory and memory.get("through_created_at") and memory.get("through_message_id"):
                    sql += " AND (created_at>%s OR (created_at=%s AND id>%s))"
                    params += (memory["through_created_at"], memory["through_created_at"], memory["through_message_id"])
                # 摘要游标使用 (created_at, id)，读取排序必须保持相同键避免同毫秒消息漏读。
                sql += " ORDER BY created_at ASC,id ASC"
                cursor.execute(sql, params)
                rows = cursor.fetchall() or []
                return {"summary": str(memory.get("summary", "")) if memory else "", "messages": [
                    {"role": "user" if int(row["role"]) == 1 else "assistant", "content": str(row.get("content", "")), "created_at": row["created_at"], "message_id": row["id"]}
                    for row in rows
                ]}

    # 原子更新会话滚动摘要，原始消息始终保留以便审计和重建。
    def save_chat_summary(self, conversation_id: str, summary: str, through_created_at: Any, through_message_id: str) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO agent_conversation_memory
                    (conversation_id,summary,through_created_at,through_message_id,updated_at)
                    VALUES (%s,%s,%s,%s,UTC_TIMESTAMP(3)) ON DUPLICATE KEY UPDATE
                    summary=VALUES(summary),through_created_at=VALUES(through_created_at),
                    through_message_id=VALUES(through_message_id),updated_at=UTC_TIMESTAMP(3)""",
                    (conversation_id, summary, through_created_at, through_message_id),
                )

    # 读取用户当前有效且未过期的长期结构化事实，按最近更新时间优先注入模型上下文。
    def list_long_term_memories(self, user_id: int) -> List[Dict[str, Any]]:
        if user_id <= 0:
            raise ValueError("用户ID无效")
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT category,memory_key,memory_value
                    FROM agent_user_long_term_memory
                    WHERE user_id=%s AND status=1
                    AND (expires_at IS NULL OR expires_at>UTC_TIMESTAMP(3))
                    ORDER BY updated_at DESC LIMIT 50""",
                    (user_id,),
                )
                return list(cursor.fetchall() or [])

    # 幂等保存模型从用户原话提取的长期事实；同一类别和键的新陈述覆盖旧值并恢复为有效状态。
    def upsert_long_term_memory(
        self,
        user_id: int,
        category: str,
        memory_key: str,
        memory_value: str,
        confidence: float,
        conversation_id: str = "",
        request_id: str = "",
    ) -> None:
        if user_id <= 0 or not category or not memory_key or not memory_value or not 0 <= confidence <= 1:
            raise ValueError("长期记忆参数无效")
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO agent_user_long_term_memory
                    (id,user_id,category,memory_key,memory_value,confidence,
                     source_conversation_id,source_request_id,status,expires_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1,NULL)
                    ON DUPLICATE KEY UPDATE
                    memory_value=VALUES(memory_value),confidence=VALUES(confidence),
                    source_conversation_id=VALUES(source_conversation_id),
                    source_request_id=VALUES(source_request_id),status=1,expires_at=NULL,
                    updated_at=UTC_TIMESTAMP(3)""",
                    (
                        str(uuid.uuid4()), user_id, category, memory_key, memory_value, confidence,
                        conversation_id or None, request_id or None,
                    ),
                )

    # 保存助手最终回答及引用快照。
    def complete_chat(self, request_id: str, answer: str, citations: Sequence[Dict[str, Any]]) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE agent_conversation_message SET status=2,content=%s,citations=%s,completed_at=UTC_TIMESTAMP(3) WHERE request_id=%s AND role=2 AND status=1", (answer, json.dumps(list(citations), ensure_ascii=False), request_id))

    # 复核引用仍属于当前用户知识库的有效索引版本，避免检索副本过期或越权落库。
    def validate_chat_citations(self, user_id: int, knowledge_base_id: int, citations: Sequence[Dict[str, Any]]) -> bool:
        if not citations:
            return True
        ids = [str(item.get("chunk_id", "")) for item in citations]
        if any(not item for item in ids):
            return False
        placeholders = ",".join(["%s"] * len(ids))
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM agent_document_chunk WHERE chunk_type=1 AND user_id=%s AND knowledge_base_id=%s AND id IN (" + placeholders + ")", (user_id, knowledge_base_id, *ids))
                row = cursor.fetchone()
                return bool(row and int(row["total"]) == len(set(ids)))

    # 按 source_chunk_id 回查当前用户知识库中的有效原文，供 Graph RAG 生成可引用证据。
    def resolve_chunks(self, source_chunk_ids: Sequence[str], user_id: int, knowledge_base_id: int, index_version: int = 0) -> List[Dict[str, Any]]:
        ids = [str(value).strip() for value in source_chunk_ids if str(value).strip()]
        if not ids or user_id <= 0 or knowledge_base_id <= 0 or index_version < 0:
            return []
        placeholders = ",".join(["%s"] * len(ids))
        sql = "SELECT id AS chunk_id, document_id, index_version, content, metadata FROM agent_document_chunk WHERE chunk_type=1 AND user_id=%s AND knowledge_base_id=%s AND id IN (" + placeholders + ")"
        params: Tuple[Any, ...] = (user_id, knowledge_base_id, *ids)
        if index_version > 0:
            sql += " AND index_version=%s"
            params += (index_version,)
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall() or []
                for row in rows:
                    try:
                        row["metadata"] = json.loads(row.get("metadata") or "{}")
                    except (TypeError, json.JSONDecodeError):
                        row["metadata"] = {}
                return list(rows)

    # 保存失败终态，客户端只接收稳定错误码。
    def fail_chat(self, request_id: str, error_code: str, message: str) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE agent_conversation_message SET status=3,error_code=%s,error_message=%s,completed_at=UTC_TIMESTAMP(3) WHERE request_id=%s AND role=2 AND status=1", (error_code, message[:500], request_id))

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
