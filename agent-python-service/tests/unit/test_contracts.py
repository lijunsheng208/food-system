"""验证 Python Agent 与 Go Logic、RocketMQ 之间的现有协议契约。"""

import json
import unittest

from familyos_agent.messaging import parse_index_event
from familyos_agent.transport.contracts import (
    COMPLETE_DOCUMENT_INDEX_METHOD,
    FAIL_DOCUMENT_INDEX_METHOD,
    GET_DOCUMENT_DOWNLOAD_TICKET_METHOD,
)

try:
    from familyos_agent.generated.knowledge.v1 import knowledge_pb2
except ModuleNotFoundError:
    knowledge_pb2 = None


class ProtocolContractTest(unittest.TestCase):
    """防止目录重构或代码生成导致既有 RPC 与消息协议漂移。"""

    # Logic 内部服务必须继续暴露 Python Indexer 使用的三个 Unary RPC。
    @unittest.skipIf(knowledge_pb2 is None, "当前 Python 环境未安装 protobuf")
    def test_logic_internal_rpc_names_match_proto(self) -> None:
        service = knowledge_pb2.DESCRIPTOR.services_by_name["KnowledgeInternalService"]
        full_names = {"/%s/%s" % (service.full_name, method.name) for method in service.methods}
        self.assertEqual(
            full_names,
            {
                GET_DOCUMENT_DOWNLOAD_TICKET_METHOD,
                COMPLETE_DOCUMENT_INDEX_METHOD,
                FAIL_DOCUMENT_INDEX_METHOD,
            },
        )

    # RocketMQ schema_version=1 的字段必须按现有 Logic Outbox 格式解析。
    def test_document_index_event_v1_contract(self) -> None:
        body = json.dumps(
            {
                "schema_version": 1,
                "event_id": "event-1",
                "event_type": "document.index.requested",
                "document_id": 11,
                "user_id": 22,
                "knowledge_base_id": 33,
                "index_version": 2,
                "occurred_at": "2026-09-11T10:00:00Z",
            }
        ).encode()
        event = parse_index_event(body)
        self.assertEqual((event.document_id, event.index_version), (11, 2))


if __name__ == "__main__":
    unittest.main()
