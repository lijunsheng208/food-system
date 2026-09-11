"""兼容 Go Logic Transactional Outbox 的 RocketMQ Consumer。"""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict

from .config import RocketMQConfig
from .domain import DocumentIndexEvent
from .transport.contracts import DOCUMENT_INDEX_EVENT_TYPE, DOCUMENT_INDEX_SCHEMA_VERSION

if TYPE_CHECKING:
    from .repositories import MySQLRepository


logger = logging.getLogger(__name__)


# 严格解析 Logic 发布的 schema_version=1 INDEX JSON 事件。
def parse_index_event(body: bytes) -> DocumentIndexEvent:
    try:
        value = json.loads(body.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("事件根节点必须是对象")
        occurred_at = datetime.fromisoformat(str(value["occurred_at"]).replace("Z", "+00:00"))
        event = DocumentIndexEvent(
            int(value["schema_version"]), str(value["event_id"]), str(value["event_type"]),
            int(value["document_id"]), int(value["user_id"]), int(value["knowledge_base_id"]),
            int(value["index_version"]), occurred_at,
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("文档索引消息无效") from exc
    if event.schema_version != DOCUMENT_INDEX_SCHEMA_VERSION or event.event_type != DOCUMENT_INDEX_EVENT_TYPE or not event.event_id or min(event.document_id, event.user_id, event.knowledge_base_id, event.index_version) <= 0:
        raise ValueError("文档索引消息必填字段或事件类型不匹配")
    return event


class RocketMQDocumentConsumer:
    """订阅与 Go Agent 相同 Topic 和 INDEX Tag，并在任务落库后 ACK。"""

    # 延迟导入原生 RocketMQ 客户端，使纯解析测试不依赖本机动态库。
    def __init__(self, config: RocketMQConfig, repository: "MySQLRepository") -> None:
        try:
            from rocketmq.client import ConsumeStatus, PushConsumer
        except ImportError as exc:
            raise RuntimeError("缺少 rocketmq-client-python 或其原生动态库") from exc
        self._consume_status = ConsumeStatus
        self._repository = repository
        self._consumer = PushConsumer(config.consumer_group)
        self._consumer.set_name_server_address(config.endpoint)
        if config.access_key:
            self._consumer.set_session_credentials(config.access_key, config.access_secret, "")
        self._consumer.subscribe(config.topic, self._receive, "INDEX")

    # 无效消息直接确认，数据库暂时失败则要求 Broker 稍后重投。
    def _receive(self, message: Any) -> Any:
        try:
            event = parse_index_event(bytes(message.body))
        except ValueError as exc:
            logger.error("丢弃无效 RocketMQ INDEX 消息: %s", exc)
            return self._consume_status.CONSUME_SUCCESS
        try:
            self._repository.record_index_event(event)
        except Exception as exc:
            logger.error("索引事件落库失败，等待 RocketMQ 重投: %s", exc)
            return self._consume_status.RECONSUME_LATER
        return self._consume_status.CONSUME_SUCCESS

    # 启动 RocketMQ PushConsumer 后台消费线程。
    def start(self) -> None:
        self._consumer.start()

    # 停止 Consumer 并释放原生客户端资源。
    def close(self) -> None:
        self._consumer.shutdown()
