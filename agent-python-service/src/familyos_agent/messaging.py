"""兼容 Go Logic Transactional Outbox 的 RocketMQ Consumer。"""

import json
from datetime import datetime

from .domain import DocumentIndexEvent
from .transport.contracts import DOCUMENT_INDEX_EVENT_TYPE, DOCUMENT_INDEX_SCHEMA_VERSION

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
