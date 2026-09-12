"""D2 Chat gRPC 流式应用服务。"""

import asyncio
import hmac
import logging
from concurrent import futures
from typing import Any, AsyncIterator, Mapping, Optional

import grpc

from ...agent.streaming import AgentEvent, stream_agent_events
from ...generated.agent.v1 import agent_pb2
from ...generated.agent.v1 import agent_pb2_grpc

logger = logging.getLogger(__name__)


class ChatStreamService:
    """将 LangGraph 事件流映射为现有 AgentChatService Proto 事件。"""

    def __init__(self, graph: Any, token: str, total_timeout: float = 60.0, conversations: Any = None) -> None:
        if graph is None or not token or total_timeout <= 0:
            raise ValueError("Chat Stream 服务配置无效")
        self._graph, self._token, self._timeout, self._conversations = graph, token, total_timeout, conversations

    # 校验内部服务令牌，避免未授权请求消耗模型和检索资源。
    def authenticate(self, context: grpc.ServicerContext) -> None:
        supplied = dict(context.invocation_metadata()).get("x-familyos-internal-token", "")
        if not hmac.compare_digest(supplied, self._token):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "内部服务认证失败")

    # 异步运行 Graph 并把模型、Tool 和引用事件转换为 Chat 事件。
    async def stream(self, state: Mapping[str, Any]) -> AsyncIterator[agent_pb2.ChatStreamEvent]:
        request_id = str(state.get("request_id", ""))
        if self._conversations is not None:
            await asyncio.to_thread(self._conversations.begin_chat, type("ChatRequest", (), state)())
        answer_parts, citations = [], []
        async for event in stream_agent_events(self._graph, state, {"configurable": {"thread_id": state.get("conversation_id", request_id)}}, self._timeout):
            if event.type == "model_token":
                answer_parts.append(event.content)
                yield agent_pb2.ChatStreamEvent(type="answer_delta", request_id=request_id, content=event.content)
            elif event.type == "tool_start":
                yield agent_pb2.ChatStreamEvent(type="tool_start", request_id=request_id, content=event.name)
            elif event.type == "tool_end":
                yield agent_pb2.ChatStreamEvent(type="tool_end", request_id=request_id, content=event.content)
            elif event.type == "citations":
                for citation in event.data.get("citations", []):
                    citations.append(dict(citation))
                    yield agent_pb2.ChatStreamEvent(type="citation", request_id=request_id, citation=agent_pb2.ChatCitation(**dict(citation)))
            elif event.type == "error":
                yield agent_pb2.ChatStreamEvent(type="error", request_id=request_id, error_code="AGENT_FAILED", error_message="Agent 执行失败")
        if self._conversations is not None:
            await asyncio.to_thread(self._conversations.complete_chat, request_id, "".join(answer_parts), citations)
        yield agent_pb2.ChatStreamEvent(type="completed", request_id=request_id)


class AgentChatGrpcServer:
    """使用标准生成 Servicer 基类暴露 agent.v1 ChatStream。"""

    def __init__(self, port: int, service: ChatStreamService, conversations: Any = None, max_workers: int = 8) -> None:
        if port <= 0 or service is None or max_workers <= 0:
            raise ValueError("Agent Chat gRPC 配置无效")
        self._service, self._conversations = service, conversations
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
        agent_pb2_grpc.add_AgentChatServiceServicer_to_server(
            _AgentChatServicer(service), self._server
        )
        if self._server.add_insecure_port("[::]:%d" % port) == 0:
            raise RuntimeError("Agent Chat gRPC 端口绑定失败")

    # 启动 gRPC Server。
    def start(self) -> None:
        self._server.start()

    # 停止 gRPC Server 并等待流式请求结束。
    def close(self, grace: float = 5.0) -> None:
        self._server.stop(grace).wait()


class _AgentChatServicer(agent_pb2_grpc.AgentChatServiceServicer):
    """将标准 gRPC Servicer 请求适配到现有 ChatStreamService。"""

    def __init__(self, service: ChatStreamService) -> None:
        self._service = service

    # 处理 ChatStream，并在客户端取消时停止异步事件消费。
    def ChatStream(self, request: Any, context: grpc.ServicerContext):
        self._service.authenticate(context)
        state = {"user_id": request.user_id, "knowledge_base_id": request.knowledge_base_id, "conversation_id": request.conversation_id, "request_id": request.request_id, "message": request.message, "original_query": request.message}
        iterator = None
        try:
            loop = asyncio.new_event_loop()
            try:
                iterator = self._service.stream(state)
                while context.is_active():
                    try:
                        event = loop.run_until_complete(iterator.__anext__())
                    except StopAsyncIteration:
                        break
                    yield event
            finally:
                if iterator is not None:
                    loop.run_until_complete(iterator.aclose())
                loop.close()
        except TimeoutError:
            yield agent_pb2.ChatStreamEvent(type="error", request_id=request.request_id, error_code="MODEL_TIMEOUT", error_message="Agent 请求超时")
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("ChatStream 处理失败 request_id=%s", request.request_id)
            yield agent_pb2.ChatStreamEvent(type="error", request_id=request.request_id, error_code="CHAT_FAILED", error_message="问答处理失败")

    # 创建绑定用户和知识库的会话。
    def CreateConversation(self, request: Any, context: grpc.ServicerContext):
        self._service.authenticate(context)
        if self._service._conversations is None:
            context.abort(grpc.StatusCode.UNIMPLEMENTED, "会话功能未配置")
        if request.user_id <= 0 or request.knowledge_base_id <= 0:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "创建会话请求无效")
        try:
            conversation_id = self._service._conversations.create_conversation(request.user_id, request.knowledge_base_id)
        except Exception:
            context.abort(grpc.StatusCode.INTERNAL, "创建会话失败")
        return agent_pb2.CreateConversationResponse(conversation_id=conversation_id)
