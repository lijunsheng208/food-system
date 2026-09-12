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
class IngressConfig:
    """描述 Go Adapter 调用的内部 gRPC 入站配置。"""

    port: int
    token: str
    max_workers: int

@dataclass(frozen=True)
class ChatConfig:
    """描述 Chat gRPC 和模型运行参数。"""
    port: int
    token: str
    max_workers: int
    base_url: str
    api_key: str
    model: str
    timeout: float
    max_tokens: int
    max_steps: int
    max_tool_calls: int
    max_user_interrupts: int = 3
    checkpointer_dsn: str = ""
    metrics_port: int = 9108
    otel_endpoint: str = ""


@dataclass(frozen=True)
class EmbeddingConfig:
    """描述 OpenAI-compatible Embedding 接口。"""

    base_url: str
    api_key: str
    model: str
    dimensions: int
    batch_size: int
    timeout: float
    provider: str = "openai"
    model_name: str = ""
    device: str = "cpu"
    use_fp16: bool = False


@dataclass(frozen=True)
class MilvusConfig:
    """描述 Milvus 连接、Collection 和 Dense 索引参数。"""

    uri: str
    token: str
    database: str
    collection: str
    timeout: float
    dense_index_type: str
    dense_metric_type: str


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
    milvus: MilvusConfig
    opensearch: OpenSearchConfig


@dataclass(frozen=True)
class AppConfig:
    """聚合 Python 索引服务全部运行配置。"""

    database: DatabaseConfig
    logic: LogicConfig
    worker: WorkerConfig
    ingress: IngressConfig
    chat: ChatConfig
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
    logic = _section(data, "logic")
    worker = _section(data, "worker")
    ingress = _section(data, "ingress")
    chat = _section(data, "chat")
    rag = _section(data, "rag")
    embedding = _section(rag, "embedding")
    milvus = _section(rag, "milvus")
    opensearch = _section(rag, "opensearch")
    result = AppConfig(
        database=DatabaseConfig(str(_env("DATABASE_DSN", database.get("dsn", "")))),
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
        ingress=IngressConfig(
            int(_env("INGRESS_PORT", ingress.get("port", 50053))),
            str(_env("INGRESS_TOKEN", ingress.get("token", ""))),
            int(_env("INGRESS_MAX_WORKERS", ingress.get("max_workers", 8))),
        ),
        chat=ChatConfig(int(_env("CHAT_PORT", chat.get("port", 50054))), str(_env("CHAT_TOKEN", chat.get("token", ""))), int(_env("CHAT_MAX_WORKERS", chat.get("max_workers", 8))), str(_env("CHAT_BASE_URL", chat.get("base_url", "https://api.openai.com/v1"))), str(_env("CHAT_API_KEY", chat.get("api_key", ""))), str(_env("CHAT_MODEL", chat.get("model", ""))), _duration(_env("CHAT_TIMEOUT", chat.get("timeout", "60s"))), int(_env("CHAT_MAX_TOKENS", chat.get("max_tokens", 2048))), int(_env("CHAT_MAX_STEPS", chat.get("max_steps", 8))), int(_env("CHAT_MAX_TOOL_CALLS", chat.get("max_tool_calls", 6))), int(_env("CHAT_MAX_USER_INTERRUPTS", chat.get("max_user_interrupts", 3))), str(_env("CHAT_CHECKPOINTER_DSN", chat.get("checkpointer_dsn", ""))), int(_env("CHAT_METRICS_PORT", chat.get("metrics_port", 9108))), str(_env("CHAT_OTEL_ENDPOINT", chat.get("otel_endpoint", "")))),
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
                str(_env("RAG_EMBEDDING_PROVIDER", embedding.get("provider", "openai"))).lower(),
                str(_env("RAG_EMBEDDING_MODEL_NAME", embedding.get("model_name", ""))),
                str(_env("RAG_EMBEDDING_DEVICE", embedding.get("device", "cpu"))),
                str(_env("RAG_EMBEDDING_USE_FP16", embedding.get("use_fp16", False))).lower() in ("1", "true", "yes"),
            ),
            MilvusConfig(
                str(_env("RAG_MILVUS_URI", milvus.get("uri", ""))),
                str(_env("RAG_MILVUS_TOKEN", milvus.get("token", ""))),
                str(_env("RAG_MILVUS_DATABASE", milvus.get("database", ""))),
                str(_env("RAG_MILVUS_COLLECTION", milvus.get("collection", ""))),
                _duration(_env("RAG_MILVUS_TIMEOUT", milvus.get("timeout", "10s"))),
                str(_env("RAG_MILVUS_DENSE_INDEX_TYPE", milvus.get("dense_index_type", "AUTOINDEX"))).upper(),
                str(_env("RAG_MILVUS_DENSE_METRIC_TYPE", milvus.get("dense_metric_type", "COSINE"))).upper(),
            ),
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
    if not result.database.dsn:
        raise ValueError("MySQL 配置必须完整")
    if result.ingress.port <= 0 or not result.ingress.token or result.ingress.max_workers <= 0:
        raise ValueError("Ingress port、token 和 max_workers 必须有效")
    if not result.logic.target or not result.logic.agent_token:
        raise ValueError("Logic target 和 agent_token 必须完整")
    if result.chat.port <= 0 or result.chat.max_steps <= 0 or result.chat.max_tool_calls <= 0 or result.chat.max_user_interrupts <= 0 or result.chat.metrics_port <= 0:
        raise ValueError("Chat 配置边界无效")
    embedding_ready = result.rag.embedding.model_name if result.rag.embedding.provider == "bge-m3" else (result.rag.embedding.api_key and result.rag.embedding.model)
    if not embedding_ready:
        raise ValueError("Embedding 模型配置必须完整")
    if not all((result.rag.milvus.uri, result.rag.milvus.database, result.rag.milvus.collection)):
        raise ValueError("Milvus uri、database 和 collection 配置必须完整")
    if result.rag.milvus.collection != "familyos_document_chunks_v1":
        raise ValueError("阶段 A 仅允许使用 familyos_document_chunks_v1 Collection")
    if result.rag.milvus.dense_metric_type != "COSINE":
        raise ValueError("Milvus Dense 向量首期必须使用 COSINE")
    if result.rag.milvus.dense_index_type not in ("AUTOINDEX", "HNSW"):
        raise ValueError("Milvus Dense 索引类型必须是 AUTOINDEX 或 HNSW")
    if result.rag.embedding.dimensions <= 0 or result.rag.embedding.dimensions > 2000:
        raise ValueError("Embedding dimensions 必须在 1 到 2000 之间")
    if result.rag.embedding.provider == "bge-m3" and not result.rag.embedding.model_name:
        raise ValueError("BGE-M3 provider 必须配置 model_name")
    if result.rag.child_overlap >= result.rag.child_size or result.rag.parent_size < result.rag.child_size:
        raise ValueError("父子切片配置无效")
    return result
