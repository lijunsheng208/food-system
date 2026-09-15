"""OpenAI-compatible 异步 Chat 模型客户端。"""

import json
import logging
from typing import Any, AsyncIterator, Mapping, Optional, Sequence

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import PrivateAttr

from ..config import ChatConfig

logger = logging.getLogger(__name__)


class AsyncOpenAIChatModel(BaseChatModel):
    """通过 OpenAI-compatible 接口提供 LangChain 标准非流式与流式 ChatModel。"""

    _config: Any = PrivateAttr()
    _tools: tuple[Mapping[str, Any], ...] = PrivateAttr(default_factory=tuple)

    def __init__(self, config: ChatConfig, enable_streaming: bool = True) -> None:
        """校验模型配置，并控制该实例是否允许 LangChain 隐式启用流式请求。"""
        if not config.base_url or not config.api_key or not config.model:
            raise ValueError("Chat 模型配置必须完整")
        super().__init__(disable_streaming=not enable_streaming)
        self._config = config

    @property
    def _llm_type(self) -> str:
        """返回 LangChain 追踪使用的模型类型标识。"""
        return "familyos-openai-compatible"

    def bind_tools(self, tools: Sequence[Mapping[str, Any]], **kwargs: Any) -> "AsyncOpenAIChatModel":
        """返回绑定白名单 Tool 的独立模型实例，避免并发请求修改共享状态。"""
        if kwargs:
            raise ValueError("当前模型不支持额外 Tool 绑定选项")
        bound = AsyncOpenAIChatModel(self._config, enable_streaming=self.disable_streaming is not True)
        bound._tools = tuple(dict(tool) for tool in tools)
        return bound

    def _generate(self, messages: list[BaseMessage], stop: Optional[list[str]] = None, **kwargs: Any) -> ChatResult:
        """拒绝同步模型调用，Agent 服务只允许异步网络请求。"""
        raise TypeError("Chat 模型只支持异步调用")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """执行非流式模型请求，并返回 LangChain 标准完整消息。"""
        payload = self._payload(messages, stream=False, stop=stop)
        logger.info("Chat 模型请求开始 model=%s messages=%d tools=%d stream=false", self._config.model, len(messages), len(self._tools))
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.post(self._completion_url(), headers=self._headers(), json=payload)
            logger.info("Chat 模型响应 status=%d stream=false", response.status_code)
            response.raise_for_status()
            body = response.json()
        choice = body.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = [_normalize_tool_call(call) for call in (message.get("tool_calls") or [])]
        logger.info("Chat 模型消息解析 content=%s tool_calls=%d", bool(message.get("content")), len(tool_calls))
        result_message = AIMessage(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            additional_kwargs={"reasoning_content": message.get("reasoning_content", "")},
            usage_metadata=_usage_metadata(body.get("usage")),
        )
        return ChatResult(generations=[ChatGeneration(message=result_message, generation_info={"finish_reason": choice.get("finish_reason")})])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """消费模型 SSE，并把文本及分片 Tool Call 转换为 LangChain 消息块。"""
        payload = self._payload(messages, stream=True, stop=stop)
        logger.info("Chat 模型请求开始 model=%s messages=%d tools=%d stream=true", self._config.model, len(messages), len(self._tools))
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            async with client.stream("POST", self._completion_url(), headers=self._headers(), json=payload) as response:
                logger.info("Chat 模型响应 status=%d stream=true", response.status_code)
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        body = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise ValueError("Chat 模型流式事件 JSON 无效") from exc
                    chunk = _stream_generation_chunk(body)
                    if chunk is not None:
                        yield chunk

    def _payload(self, messages: Sequence[Any], stream: bool, stop: Optional[list[str]]) -> dict[str, Any]:
        """构造 OpenAI-compatible 请求体，并在 Tool 决策轮携带白名单定义。"""
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [_serialize_message(message) for message in messages],
            "max_tokens": self._config.max_tokens,
            "stream": stream,
        }
        if self._tools:
            payload["tools"] = list(self._tools)
        if stop:
            payload["stop"] = stop
        return payload

    def _completion_url(self) -> str:
        """返回 Chat Completions 接口地址。"""
        return self._config.base_url.rstrip("/") + "/chat/completions"

    def _headers(self) -> dict[str, str]:
        """构造仅包含服务端 API Key 的请求头。"""
        return {"Authorization": "Bearer " + self._config.api_key}

    async def aclose(self) -> None:
        """保留统一资源关闭接口；HTTP 客户端按请求自动关闭。"""
        return None


def _usage_metadata(value: Any) -> Optional[dict[str, int]]:
    """将 OpenAI-compatible usage 字段转换为 LangChain token 统计。"""
    if not isinstance(value, Mapping):
        return None
    input_tokens = int(value.get("prompt_tokens", value.get("input_tokens", 0)) or 0)
    output_tokens = int(value.get("completion_tokens", value.get("output_tokens", 0)) or 0)
    total_tokens = int(value.get("total_tokens", input_tokens + output_tokens) or 0)
    if input_tokens <= 0 and output_tokens <= 0 and total_tokens <= 0:
        return None
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


def _stream_generation_chunk(body: Any) -> Optional[ChatGenerationChunk]:
    """把单个 OpenAI-compatible SSE 数据帧转换为可聚合的消息块。"""
    if not isinstance(body, Mapping):
        raise ValueError("Chat 模型流式事件必须是 JSON 对象")
    choices = body.get("choices") or []
    usage = _usage_metadata(body.get("usage"))
    if not choices:
        if usage is None:
            return None
        return ChatGenerationChunk(message=AIMessageChunk(content="", usage_metadata=usage))
    choice = choices[0]
    delta = choice.get("delta") or {}
    if not isinstance(delta, Mapping):
        raise ValueError("Chat 模型流式 delta 格式无效")
    tool_chunks = []
    for position, call in enumerate(delta.get("tool_calls") or []):
        if not isinstance(call, Mapping):
            raise ValueError("Chat 模型流式 Tool Call 格式无效")
        function = call.get("function") or {}
        if not isinstance(function, Mapping):
            raise ValueError("Chat 模型流式 Tool 函数格式无效")
        arguments = function.get("arguments", "")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False)
        tool_chunks.append({
            "name": str(function.get("name") or "") or None,
            "args": arguments,
            "id": str(call.get("id") or "") or None,
            "index": int(call.get("index", position)),
            "type": "tool_call_chunk",
        })
    finish_reason = choice.get("finish_reason")
    generation_info = {"finish_reason": finish_reason} if finish_reason else None
    content = delta.get("content") or ""
    reasoning = delta.get("reasoning_content") or ""
    if not content and not reasoning and not tool_chunks and usage is None and generation_info is None:
        return None
    message = AIMessageChunk(
        content=str(content),
        tool_call_chunks=tool_chunks,
        additional_kwargs={"reasoning_content": str(reasoning)} if reasoning else {},
        usage_metadata=usage,
    )
    return ChatGenerationChunk(message=message, generation_info=generation_info)


def _serialize_message(message: Any) -> Mapping[str, Any]:
    """将 LangChain 消息转换为 OpenAI-compatible API 所需的字典格式。"""
    if isinstance(message, Mapping):
        return dict(message)
    result = {"role": getattr(message, "type", "user"), "content": getattr(message, "content", "")}
    if result["role"] == "human":
        result["role"] = "user"
    if result["role"] == "ai":
        result["role"] = "assistant"
        calls = getattr(message, "tool_calls", []) or []
        if calls:
            result["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}} for c in calls]
    if result["role"] == "tool":
        result["tool_call_id"] = getattr(message, "tool_call_id", "")
        result["name"] = getattr(message, "name", "")
    return result


def _normalize_tool_call(call: Mapping[str, Any]) -> Mapping[str, Any]:
    """将完整 OpenAI-compatible Tool Call 转换为 LangChain 标准结构。"""
    function = call.get("function", {}) if isinstance(call, Mapping) else {}
    arguments = function.get("arguments", {}) if isinstance(function, Mapping) else {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            arguments = {}
    return {
        "name": str(function.get("name", "")),
        "args": arguments if isinstance(arguments, Mapping) else {},
        "id": str(call.get("id", "")),
        "type": "tool_call",
    }
