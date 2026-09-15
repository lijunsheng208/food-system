"""验证 Python Agent 调用 Logic 内部业务接口。"""

import unittest
from unittest.mock import patch

from familyos_agent.clients import LogicClient
from familyos_agent.config import LogicConfig
from familyos_agent.generated.auth.v1 import auth_pb2
from familyos_agent.transport.contracts import INTERNAL_TOKEN_HEADER, LIST_DIETARY_PREFERENCES_METHOD


class FakeUnaryCall:
    """记录 Unary RPC 请求参数并返回预设响应。"""

    def __init__(self, response=None):
        """初始化响应和调用记录。"""
        self.response = response
        self.calls = []

    def __call__(self, request, timeout=None, metadata=None):
        """记录请求、超时和 metadata。"""
        self.calls.append((request, timeout, metadata))
        return self.response


class FakeChannel:
    """按 RPC 路径提供测试 Unary 方法。"""

    def __init__(self, dietary_response):
        """初始化饮食偏好 RPC 和其他占位 RPC。"""
        self.dietary = FakeUnaryCall(dietary_response)
        self.other = FakeUnaryCall()

    def unary_unary(self, method, request_serializer=None, response_deserializer=None):
        """为饮食偏好路径返回可记录调用对象。"""
        return self.dietary if method == LIST_DIETARY_PREFERENCES_METHOD else self.other

    def close(self):
        """模拟关闭 gRPC Channel。"""


class LogicClientTest(unittest.TestCase):
    """验证 LogicClient 的饮食偏好接口契约和身份边界。"""

    def test_lists_dietary_preferences_with_internal_identity(self):
        """验证 RPC 携带内部 Token，并只使用调用方提供的服务端用户 ID。"""
        response = auth_pb2.ListDietaryPreferencesResponse(
            code=0,
            preferences=[auth_pb2.DietaryPreferenceInfo(preference_type=5, preference_value="花生", note="严重过敏")],
        )
        channel = FakeChannel(response)
        with patch("familyos_agent.clients.implementations.grpc.insecure_channel", return_value=channel):
            client = LogicClient(LogicConfig("127.0.0.1:50051", "internal-token", 5.0))

        result = client.list_dietary_preferences(7)

        self.assertEqual(result, [{"preference_type": 5, "preference_value": "花生", "note": "严重过敏"}])
        request, timeout, metadata = channel.dietary.calls[0]
        self.assertEqual(request.user_id, 7)
        self.assertEqual(timeout, 5.0)
        self.assertEqual(metadata, ((INTERNAL_TOKEN_HEADER, "internal-token"),))

    def test_rejects_invalid_dietary_user(self):
        """验证无效用户 ID 不会发起越权查询。"""
        channel = FakeChannel(auth_pb2.ListDietaryPreferencesResponse(code=0))
        with patch("familyos_agent.clients.implementations.grpc.insecure_channel", return_value=channel):
            client = LogicClient(LogicConfig("127.0.0.1:50051", "internal-token", 5.0))

        with self.assertRaisesRegex(ValueError, "用户无效"):
            client.list_dietary_preferences(0)
        self.assertEqual(channel.dietary.calls, [])


if __name__ == "__main__":
    unittest.main()
