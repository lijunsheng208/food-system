"""LangGraph Checkpointer 构造和 D3 的持久化边界。"""

import sqlite3
from pathlib import Path
from typing import Any, Optional

from .mysql_checkpointer import MySQLCheckpointSaver


def build_checkpointer(dsn: Optional[str] = None) -> Any:
    """构造生产可持久化或开发内存 Checkpointer。"""
    if dsn:
        if dsn.startswith("mysql://") or dsn.startswith("mysql+") or "@tcp(" in dsn:
            return MySQLCheckpointSaver(dsn.removeprefix("mysql://"))
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:
            raise RuntimeError("配置了 checkpointer_dsn，但未安装 langgraph-checkpoint-sqlite") from exc
        path = dsn.removeprefix("sqlite:///")
        if not path:
            raise ValueError("checkpointer_dsn 不能为空")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, check_same_thread=False)
        saver = SqliteSaver(connection)
        if hasattr(saver, "setup"):
            saver.setup()
        return saver
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except ImportError as exc:
        raise RuntimeError("缺少 langgraph Checkpointer 依赖") from exc
    return MemorySaver()
