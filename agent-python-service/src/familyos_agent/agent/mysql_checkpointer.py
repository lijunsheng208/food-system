"""基于 MySQL 的 LangGraph Checkpoint 持久化实现。"""

import asyncio
import json
from typing import Any, AsyncIterator, Iterator, Mapping, Optional, Sequence

import pymysql
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple, get_checkpoint_id

from ..repositories.implementations import parse_mysql_dsn


class MySQLCheckpointSaver(BaseCheckpointSaver[str]):
    """把 Graph 状态和 pending writes 持久化到 FamilyOS MySQL。"""

    def __init__(self, dsn: str) -> None:
        super().__init__()
        self._params = parse_mysql_dsn(dsn)

    def _connect(self) -> Any:
        """创建独立连接，避免 Graph 并发运行共享连接。"""
        return pymysql.connect(**self._params)

    def put(self, config: Mapping[str, Any], checkpoint: Mapping[str, Any], metadata: Mapping[str, Any], new_versions: Mapping[str, Any]) -> dict[str, Any]:
        """原子保存 checkpoint，并返回包含新版本号的配置。"""
        configurable = config.get("configurable", {})
        thread_id = str(configurable["thread_id"])
        namespace = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])
        parent_id = configurable.get("checkpoint_id")
        payload_type, payload = self.serde.dumps_typed(dict(checkpoint))
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO agent_graph_checkpoint
                    (thread_id,checkpoint_ns,checkpoint_id,parent_checkpoint_id,payload_type,checkpoint_payload,metadata_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE checkpoint_payload=VALUES(checkpoint_payload), metadata_json=VALUES(metadata_json)""",
                    (thread_id, namespace, checkpoint_id, parent_id, payload_type, payload, json.dumps(dict(metadata), ensure_ascii=False)))
            conn.commit()
        finally:
            conn.close()
        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": namespace, "checkpoint_id": checkpoint_id}}

    def get_tuple(self, config: Mapping[str, Any]) -> Optional[CheckpointTuple]:
        """读取指定 checkpoint，未指定版本时读取同一 Thread 最新版本。"""
        c = config["configurable"]
        thread_id, namespace = str(c["thread_id"]), str(c.get("checkpoint_ns", ""))
        checkpoint_id = get_checkpoint_id(config)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if checkpoint_id:
                    cur.execute("SELECT * FROM agent_graph_checkpoint WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s", (thread_id, namespace, checkpoint_id))
                else:
                    cur.execute("SELECT * FROM agent_graph_checkpoint WHERE thread_id=%s AND checkpoint_ns=%s ORDER BY checkpoint_id DESC LIMIT 1", (thread_id, namespace))
                row = cur.fetchone()
                if not row:
                    return None
                actual = {"configurable": {"thread_id": thread_id, "checkpoint_ns": namespace, "checkpoint_id": row["checkpoint_id"]}}
                cur.execute("SELECT task_id,channel,payload_type,value_payload FROM agent_graph_checkpoint_write WHERE thread_id=%s AND checkpoint_ns=%s AND checkpoint_id=%s ORDER BY task_id,write_index", (thread_id, namespace, row["checkpoint_id"]))
                writes = [(w["task_id"], w["channel"], self.serde.loads_typed((w["payload_type"], w["value_payload"]))) for w in cur.fetchall()]
                parent = {"configurable": {"thread_id": thread_id, "checkpoint_ns": namespace, "checkpoint_id": row["parent_checkpoint_id"]}} if row["parent_checkpoint_id"] else None
                return CheckpointTuple(actual, self.serde.loads_typed((row["payload_type"], row["checkpoint_payload"])), json.loads(row["metadata_json"]), parent, writes)
        finally:
            conn.close()

    def list(self, config: Optional[Mapping[str, Any]], *, filter: Optional[dict[str, Any]] = None, before: Optional[Mapping[str, Any]] = None, limit: Optional[int] = None) -> Iterator[CheckpointTuple]:
        """按 Thread 倒序枚举 checkpoint，供恢复和运维检查使用。"""
        c = (config or {}).get("configurable", {})
        thread_id, namespace = c.get("thread_id"), c.get("checkpoint_ns", "")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                sql = "SELECT * FROM agent_graph_checkpoint WHERE checkpoint_ns=%s"
                args: list[Any] = [namespace]
                if thread_id is not None:
                    sql += " AND thread_id=%s"; args.append(str(thread_id))
                sql += " ORDER BY checkpoint_id DESC"
                if limit: sql += " LIMIT %s"; args.append(limit)
                cur.execute(sql, args)
                rows = cur.fetchall()
            for row in rows:
                yield CheckpointTuple({"configurable": {"thread_id": row["thread_id"], "checkpoint_ns": row["checkpoint_ns"], "checkpoint_id": row["checkpoint_id"]}}, self.serde.loads_typed((row["payload_type"], row["checkpoint_payload"])), json.loads(row["metadata_json"]), None, [])
        finally:
            conn.close()

    def put_writes(self, config: Mapping[str, Any], writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None:
        """幂等保存节点中间 writes，支持恢复时重放 pending 状态。"""
        c = config["configurable"]; thread_id, namespace, checkpoint_id = str(c["thread_id"]), str(c.get("checkpoint_ns", "")), str(c["checkpoint_id"])
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                for index, (channel, value) in enumerate(writes):
                    kind, payload = self.serde.dumps_typed(value)
                    cur.execute("""INSERT IGNORE INTO agent_graph_checkpoint_write
                        (thread_id,checkpoint_ns,checkpoint_id,task_id,task_path,write_index,channel,payload_type,value_payload)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (thread_id, namespace, checkpoint_id, task_id, task_path, index, channel, kind, payload))
            conn.commit()
        finally:
            conn.close()

    def delete_thread(self, thread_id: str) -> None:
        """删除指定 Thread 的 checkpoint 和 writes。"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM agent_graph_checkpoint_write WHERE thread_id=%s", (thread_id,))
                cur.execute("DELETE FROM agent_graph_checkpoint WHERE thread_id=%s", (thread_id,))
            conn.commit()
        finally:
            conn.close()

    async def aget_tuple(self, config: Mapping[str, Any]) -> Optional[CheckpointTuple]:
        """异步读取 checkpoint，避免阻塞事件循环。"""
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(self, config: Mapping[str, Any], checkpoint: Mapping[str, Any], metadata: Mapping[str, Any], new_versions: Mapping[str, Any]) -> dict[str, Any]:
        """异步保存 checkpoint。"""
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(self, config: Mapping[str, Any], writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None:
        """异步保存 pending writes。"""
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        """异步删除 Thread 状态。"""
        await asyncio.to_thread(self.delete_thread, thread_id)

    async def alist(self, config: Optional[Mapping[str, Any]], *, filter: Optional[dict[str, Any]] = None, before: Optional[Mapping[str, Any]] = None, limit: Optional[int] = None) -> AsyncIterator[CheckpointTuple]:
        """异步枚举 checkpoint。"""
        for item in await asyncio.to_thread(lambda: list(self.list(config, filter=filter, before=before, limit=limit))):
            yield item
