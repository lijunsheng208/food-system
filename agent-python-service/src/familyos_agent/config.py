"""从 YAML 和 FAMILYOS_AGENT_ 环境变量加载索引服务配置。"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class DatabaseConfig:
    """描述 Agent MySQL 连接。"""

    dsn: str


@dataclass(frozen=True)
class RocketMQConfig:
    """描述与 Go Agent 兼容的 RocketMQ 消费参数。"""

    endpoint: str
    access_key: str
    access_secret: str
    consumer_group: str
    topic: str


@dataclass(frozen=True)
class LogicConfig:
    """描述 Logic 内部 gRPC 连接。"""

    target: str
    agent_token: str
    request_timeout: float


@dataclass(frozen=True)
class WorkerConfig:
    """描述任务领取、锁恢复和重试参数。"""

    poll_interval: float
    lock_timeout: float
    retry_base: float
    retry_max: float
    max_attempts: int


@dataclass(frozen=True)
class EmbeddingConfig:
    """描述 OpenAI-compatible Embedding 接口。"""

    base_url: str
    api_key: str
    model: str
    dimensions: int
    batch_size: int
    timeout: float


@dataclass(frozen=True)
class OpenSearchConfig:
    """描述子块 BM25 索引连接。"""

    enabled: bool
    endpoint: str
    username: str
    password: str
    index: str
    timeout: float


@dataclass(frozen=True)
class RAGConfig:
    """描述解析、父子切片和索引存储参数。"""

    child_size: int
    child_overlap: int
    parent_size: int
    max_file_size: int
    download_timeout: float
    embedding: EmbeddingConfig
    pgvector_dsn: str
    opensearch: OpenSearchConfig


@dataclass(frozen=True)
class AppConfig:
    """聚合 Python 索引服务全部运行配置。"""

    database: DatabaseConfig
    rocketmq: RocketMQConfig
    logic: LogicConfig
    worker: WorkerConfig
    rag: RAGConfig


# 将 Go 风格的 5m、30s 等持续时间解析为秒。
def _duration(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h)\s*", str(value))
    if not match:
        raise ValueError("无效持续时间: %s" % value)
    factors = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return float(match.group(1)) * factors[match.group(2)]


# 优先读取环境变量，使密钥不必写入配置文件。
def _env(name: str, fallback: Any = "") -> Any:
    return os.getenv("FAMILYOS_AGENT_" + name, fallback)


# 从嵌套字典安全取得配置段。
def _section(data: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError("配置段 %s 必须是对象" % name)
    return value


# 加载并严格校验索引 Worker 所需配置。
def load_config(path: Optional[str] = None) -> AppConfig:
    config_path = Path(path or os.getenv("FAMILYOS_AGENT_CONFIG", "config/config.yaml"))
    data: Dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("配置文件根节点必须是对象")
        data = loaded
    database = _section(data, "database")
    rocketmq = _section(data, "rocketmq")
    logic = _section(data, "logic")
    worker = _section(data, "worker")
    rag = _section(data, "rag")
    embedding = _section(rag, "embedding")
    pgvector = _section(rag, "pgvector")
    opensearch = _section(rag, "opensearch")
    result = AppConfig(
        database=DatabaseConfig(str(_env("DATABASE_DSN", database.get("dsn", "")))),
        rocketmq=RocketMQConfig(
            str(_env("ROCKETMQ_ENDPOINT", rocketmq.get("endpoint", ""))),
            str(_env("ROCKETMQ_ACCESS_KEY", rocketmq.get("access_key", ""))),
            str(_env("ROCKETMQ_ACCESS_SECRET", rocketmq.get("access_secret", ""))),
            str(_env("ROCKETMQ_CONSUMER_GROUP", rocketmq.get("consumer_group", "familyos-agent-document-indexer"))),
            str(_env("ROCKETMQ_TOPIC", rocketmq.get("topic", "familyos-rag-document"))),
        ),
        logic=LogicConfig(
            str(_env("LOGIC_TARGET", logic.get("target", ""))),
            str(_env("LOGIC_AGENT_TOKEN", logic.get("agent_token", ""))),
            _duration(_env("LOGIC_REQUEST_TIMEOUT", logic.get("request_timeout", "10s"))),
        ),
        worker=WorkerConfig(
            _duration(_env("WORKER_POLL_INTERVAL", worker.get("poll_interval", "1s"))),
            _duration(_env("WORKER_LOCK_TIMEOUT", worker.get("lock_timeout", "5m"))),
            _duration(_env("WORKER_RETRY_BASE", worker.get("retry_base", "5s"))),
            _duration(_env("WORKER_RETRY_MAX", worker.get("retry_max", "5m"))),
            int(_env("WORKER_MAX_ATTEMPTS", worker.get("max_attempts", 5))),
        ),
        rag=RAGConfig(
            int(_env("RAG_CHILD_SIZE", rag.get("child_size", 500))),
            int(_env("RAG_CHILD_OVERLAP", rag.get("child_overlap", 50))),
            int(_env("RAG_PARENT_SIZE", rag.get("parent_size", 4000))),
            int(_env("RAG_MAX_FILE_SIZE", rag.get("max_file_size", 20971520))),
            _duration(_env("RAG_DOWNLOAD_TIMEOUT", rag.get("download_timeout", "30s"))),
            EmbeddingConfig(
                str(_env("RAG_EMBEDDING_BASE_URL", embedding.get("base_url", "https://api.openai.com/v1"))),
                str(_env("RAG_EMBEDDING_API_KEY", embedding.get("api_key", ""))),
                str(_env("RAG_EMBEDDING_MODEL", embedding.get("model", ""))),
                int(_env("RAG_EMBEDDING_DIMENSIONS", embedding.get("dimensions", 0))),
                int(_env("RAG_EMBEDDING_BATCH_SIZE", embedding.get("batch_size", 16))),
                _duration(_env("RAG_EMBEDDING_TIMEOUT", embedding.get("timeout", "30s"))),
            ),
            str(_env("RAG_PGVECTOR_DSN", pgvector.get("dsn", ""))),
            OpenSearchConfig(
                str(_env("RAG_OPENSEARCH_ENABLED", opensearch.get("enabled", False))).lower() in ("1", "true", "yes"),
                str(_env("RAG_OPENSEARCH_ENDPOINT", opensearch.get("endpoint", ""))),
                str(_env("RAG_OPENSEARCH_USERNAME", opensearch.get("username", ""))),
                str(_env("RAG_OPENSEARCH_PASSWORD", opensearch.get("password", ""))),
                str(_env("RAG_OPENSEARCH_INDEX", opensearch.get("index", "familyos-chunks-active"))),
                _duration(_env("RAG_OPENSEARCH_REQUEST_TIMEOUT", opensearch.get("request_timeout", "5s"))),
            ),
        ),
    )
    if not all((result.database.dsn, result.rocketmq.endpoint, result.rocketmq.consumer_group, result.rocketmq.topic)):
        raise ValueError("MySQL 和 RocketMQ 配置必须完整")
    if bool(result.rocketmq.access_key) != bool(result.rocketmq.access_secret):
        raise ValueError("RocketMQ access_key 和 access_secret 必须同时配置")
    if not all((result.logic.target, result.logic.agent_token, result.rag.embedding.api_key, result.rag.embedding.model, result.rag.pgvector_dsn)):
        raise ValueError("Logic、Embedding 和 pgvector 配置必须完整")
    if result.rag.embedding.dimensions <= 0 or result.rag.embedding.dimensions > 2000:
        raise ValueError("Embedding dimensions 必须在 1 到 2000 之间")
    if result.rag.child_overlap >= result.rag.child_size or result.rag.parent_size < result.rag.child_size:
        raise ValueError("父子切片配置无效")
    return result

