"""OpenAI-compatible 异步 Chat 模型客户端。"""

from typing import Any, AsyncIterator, Mapping, Sequence
import logging
import httpx
from ..config import ChatConfig

logger = logging.getLogger(__name__)


class AsyncOpenAIChatModel:
    """提供 ainvoke、astream 和 bind_tools，供 LangGraph 异步节点使用。"""
    def __init__(self, config: ChatConfig) -> None:
        if not config.base_url or not config.api_key or not config.model:
            raise ValueError("Chat 模型配置必须完整")
        self._config = config
        self._tools = []

    # 绑定服务端 Tool 定义，模型只能从白名单中选择。
    def bind_tools(self, tools: Sequence[Mapping[str, Any]]) -> "AsyncOpenAIChatModel":
        self._tools = list(tools)
        return self

    # 异步执行一次模型决策。
    async def ainvoke(self, messages: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        payload = {"model": self._config.model, "messages": [_serialize_message(message) for message in messages], "tools": self._tools or None, "max_tokens": self._config.max_tokens, "stream": False}
        logger.info("Chat 模型请求开始 model=%s messages=%d tools=%d", self._config.model, len(messages), len(self._tools))
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.post(self._config.base_url.rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + self._config.api_key}, json=payload)
            logger.info("Chat 模型响应 status=%d", response.status_code)
            response.raise_for_status()
            body = response.json()
        message = body.get("choices", [{}])[0].get("message", {})
        logger.info("Chat 模型消息解析 content=%s tool_calls=%d", bool(message.get("content")), len(message.get("tool_calls") or []))
        try:
            from langchain_core.messages import AIMessage
            return AIMessage(content=message.get("content") or "", tool_calls=[_normalize_tool_call(call) for call in (message.get("tool_calls") or [])], additional_kwargs={"reasoning_content": message.get("reasoning_content", "")})
        except ImportError:
            return message

    # 异步流式生成最终回答文本块。
    async def astream(self, messages: Sequence[Mapping[str, Any]]) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            async with client.stream("POST", self._config.base_url.rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + self._config.api_key}, json={"model": self._config.model, "messages": [_serialize_message(message) for message in messages], "max_tokens": self._config.max_tokens, "stream": True}) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line[6:] != "[DONE]":
                        payload = __import__("json").loads(line[6:])
                        content = payload.get("choices", [{}])[0].get("delta", {}).get("content")
                        if content:
                            yield content

    # 关闭异步 HTTP 连接池。
    async def aclose(self) -> None:
        return None


# 将 LangChain 消息转换为 OpenAI-compatible API 所需的字典格式。
def _serialize_message(message: Any) -> Mapping[str, Any]:
    if isinstance(message, Mapping):
        return dict(message)
    result = {"role": getattr(message, "type", "user"), "content": getattr(message, "content", "")}
    if result["role"] == "human":
        result["role"] = "user"
    if result["role"] == "ai":
        result["role"] = "assistant"
        calls = getattr(message, "tool_calls", []) or []
        if calls:
            result["tool_calls"] = [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": __import__("json").dumps(c["args"], ensure_ascii=False)}} for c in calls]
    if result["role"] == "tool":
        result["tool_call_id"] = getattr(message, "tool_call_id", "")
        result["name"] = getattr(message, "name", "")
    return result


# 将 OpenAI-compatible Tool Call 转换为 LangChain AIMessage 的标准结构。
def _normalize_tool_call(call: Mapping[str, Any]) -> Mapping[str, Any]:
    function = call.get("function", {}) if isinstance(call, Mapping) else {}
    arguments = function.get("arguments", {}) if isinstance(function, Mapping) else {}
    if isinstance(arguments, str):
        try:
            arguments = __import__("json").loads(arguments)
        except ValueError:
            arguments = {}
    return {
        "name": str(function.get("name", "")),
        "args": arguments if isinstance(arguments, Mapping) else {},
        "id": str(call.get("id", "")),
        "type": "tool_call",
    }
