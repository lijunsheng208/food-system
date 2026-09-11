"""文档索引事件内部 gRPC 入站服务。"""

import hmac
from concurrent import futures
from typing import Any

import grpc

from ...generated.agent.v1 import agent_pb2
from ...messaging import parse_index_event
from ..contracts import INTERNAL_TOKEN_HEADER


class DocumentIndexIngressServer:
    """接收 Go Adapter 转发的 RocketMQ 事件并可靠写入任务表。"""

    # 创建绑定指定端口的 gRPC Server，repository 负责事务和业务幂等。
    def __init__(self, port: int, token: str, repository: Any, max_workers: int = 8) -> None:
        if port <= 0 or not token or max_workers <= 0:
            raise ValueError("索引事件 Ingress 配置无效")
        self._token = token
        self._repository = repository
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
        handler = grpc.unary_unary_rpc_method_handler(
            self._accept,
            request_deserializer=agent_pb2.AcceptDocumentIndexEventRequest.FromString,
            response_serializer=agent_pb2.AcceptDocumentIndexEventResponse.SerializeToString,
        )
        self._server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler("agent.v1.DocumentIndexIngressService", {"AcceptDocumentIndexEvent": handler}),))
        if self._server.add_insecure_port("[::]:%d" % port) == 0:
            raise RuntimeError("索引事件 Ingress 端口绑定失败")

    # start 启动 gRPC 后台线程，调用方继续运行任务 Worker。
    def start(self) -> None:
        self._server.start()

    # close 停止接收新事件，并等待正在落库的请求完成。
    def close(self, grace: float = 5.0) -> None:
        self._server.stop(grace).wait()

    # _accept 验证内部身份和消息契约，事务提交后才返回 ACK 条件。
    def _accept(self, request: Any, context: grpc.ServicerContext) -> Any:
        metadata = dict(context.invocation_metadata())
        supplied = metadata.get(INTERNAL_TOKEN_HEADER, "")
        if not hmac.compare_digest(supplied, self._token):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "内部服务认证失败")
        try:
            event = parse_index_event(bytes(request.event_payload))
        except ValueError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        try:
            inserted = self._repository.record_index_event(event)
        except Exception:
            context.abort(grpc.StatusCode.UNAVAILABLE, "索引任务暂时无法落库")
        return agent_pb2.AcceptDocumentIndexEventResponse(duplicate=not inserted)
