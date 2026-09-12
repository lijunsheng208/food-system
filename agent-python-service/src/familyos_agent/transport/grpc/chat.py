"""D2 Chat gRPC 流式应用服务。"""

import asyncio
import hmac
import logging
import time
from concurrent import futures
from typing import Any, AsyncIterator, Mapping, Optional

import grpc

from ...agent.streaming import AgentEvent, stream_agent_events
from ...agent.observability import AgentMetrics, trace_run
from ...generated.agent.v1 import agent_pb2
from ...generated.agent.v1 import agent_pb2_grpc

logger = logging.getLogger(__name__)


class ChatStreamService:
    """将 LangGraph 事件流映射为现有 AgentChatService Proto 事件。"""

    def __init__(self, graph: Any, token: str, total_timeout: float = 60.0, conversations: Any = None, metrics: Any = None) -> None:
        if graph is None or not token or total_timeout <= 0:
            raise ValueError("Chat Stream 服务配置无效")
        self._graph, self._token, self._timeout, self._conversations, self._metrics = graph, token, total_timeout, conversations, metrics or AgentMetrics()

    # 校验内部服务令牌，避免未授权请求消耗模型和检索资源。
    def authenticate(self, context: grpc.ServicerContext) -> None:
        supplied = dict(context.invocation_metadata()).get("x-familyos-internal-token", "")
        if not hmac.compare_digest(supplied, self._token):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "内部服务认证失败")

    # 异步运行 Graph 并把模型、Tool 和引用事件转换为 Chat 事件。
    async def stream(self, state: Mapping[str, Any]) -> AsyncIterator[agent_pb2.ChatStreamEvent]:
        request_id = str(state.get("request_id", ""))
        self._metrics.start(request_id)
        span = trace_run(request_id)
        span.__enter__()
        if self._conversations is not None:
            await asyncio.to_thread(self._conversations.begin_chat, type("ChatRequest", (), state)())
            existing = await asyncio.to_thread(self._conversations.get_chat_result, request_id) if hasattr(self._conversations, "get_chat_result") else None
            # 已完成或已失败的 request_id 只回放终态，不再次运行 Graph。
            if existing and int(existing.get("status", 1)) in (2, 3):
                if int(existing["status"]) == 3:
                    yield agent_pb2.ChatStreamEvent(type="error", request_id=request_id, error_code=existing.get("error_code", "CHAT_FAILED"), error_message=existing.get("error_message", "问答处理失败"))
                else:
                    if existing.get("content"):
                        yield agent_pb2.ChatStreamEvent(type="answer_delta", request_id=request_id, content=existing["content"])
                    yield agent_pb2.ChatStreamEvent(type="completed", request_id=request_id)
                self._metrics.finish(request_id, "replayed")
                return
        run_state = dict(state)
        # 已有等待态时使用同一 Thread 恢复；读取失败不伪造恢复状态。
        if hasattr(self._graph, "get_state") and state.get("conversation_id") and state.get("message"):
            try:
                snapshot = await asyncio.to_thread(self._graph.get_state, {"configurable": {"thread_id": state.get("conversation_id")}})
                values = getattr(snapshot, "values", snapshot.get("values", {}) if isinstance(snapshot, Mapping) else {})
                if isinstance(values, Mapping) and values.get("terminal_status") == "awaiting_input":
                    run_state["__resume__"] = state.get("message")
            except Exception:
                logger.exception("读取 Agent 等待态失败 conversation_id=%s", state.get("conversation_id"))
        answer_parts, citations = [], []
        awaiting_input = False
        failed = False
        first_token_seen = False
        node_started: dict[str, float] = {}
        async for event in stream_agent_events(self._graph, run_state, {"configurable": {"thread_id": state.get("conversation_id", request_id)}}, self._timeout):
            if event.type == "model_token":
                usage = event.data.get("usage_metadata", {}) if isinstance(event.data, Mapping) else {}
                if hasattr(self._metrics, "tokens") and isinstance(usage, Mapping):
                    self._metrics.tokens(int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)))
                if not first_token_seen:
                    first_token_seen = True
                    if hasattr(self._metrics, "first_token"):
                        self._metrics.first_token(request_id)
                answer_parts.append(event.content)
                yield agent_pb2.ChatStreamEvent(type="answer_delta", request_id=request_id, content=event.content)
            elif event.type == "tool_start":
                node_started[event.name] = time.monotonic()
                yield agent_pb2.ChatStreamEvent(type="tool_start", request_id=request_id, content=event.name)
            elif event.type == "tool_end":
                started = node_started.pop(event.name, None)
                if started is not None and hasattr(self._metrics, "node"):
                    self._metrics.node(event.name, time.monotonic() - started)
                yield agent_pb2.ChatStreamEvent(type="tool_end", request_id=request_id, content=event.content)
            elif event.type == "citations":
                for citation in event.data.get("citations", []):
                    citations.append(dict(citation))
                    yield agent_pb2.ChatStreamEvent(type="citation", request_id=request_id, citation=agent_pb2.ChatCitation(**dict(citation)))
            elif event.type == "awaiting_input":
                awaiting_input = True
                yield agent_pb2.ChatStreamEvent(type="awaiting_input", request_id=request_id, content=event.content)
            elif event.type == "error":
                failed = True
                yield agent_pb2.ChatStreamEvent(type="error", request_id=request_id, error_code=str(event.data.get("error_code", "AGENT_FAILED")), error_message="Agent 执行失败")
        if self._conversations is not None and not awaiting_input and not failed:
            if citations and hasattr(self._conversations, "validate_chat_citations"):
                valid = await asyncio.to_thread(self._conversations.validate_chat_citations, int(state.get("user_id", 0)), int(state.get("knowledge_base_id", 0)), citations)
                if not valid:
                    failed = True
                    await asyncio.to_thread(self._conversations.fail_chat, request_id, "CITATION_NOT_FOUND", "引用校验失败")
                    yield agent_pb2.ChatStreamEvent(type="error", request_id=request_id, error_code="CITATION_NOT_FOUND", error_message="引用校验失败")
        if self._conversations is not None and not awaiting_input and not failed:
            await asyncio.to_thread(self._conversations.complete_chat, request_id, "".join(answer_parts), citations)
        elif self._conversations is not None and failed:
            await asyncio.to_thread(self._conversations.fail_chat, request_id, "AGENT_FAILED", "Agent 执行失败")
        if not awaiting_input and not failed:
            self._metrics.finish(request_id, "completed")
            yield agent_pb2.ChatStreamEvent(type="completed", request_id=request_id)
        elif failed:
            self._metrics.finish(request_id, "failed")
        else:
            self._metrics.finish(request_id, "awaiting_input")
        span.__exit__(None, None, None)


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
