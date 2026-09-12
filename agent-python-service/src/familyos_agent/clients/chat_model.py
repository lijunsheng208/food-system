"""OpenAI-compatible 异步 Chat 模型客户端。"""

from typing import Any, AsyncIterator, Mapping, Sequence
import httpx
from ..config import ChatConfig


class AsyncOpenAIChatModel:
    """提供 ainvoke、astream 和 bind_tools，供 LangGraph 异步节点使用。"""
    def __init__(self, config: ChatConfig) -> None:
        if not config.base_url or not config.api_key or not config.model:
            raise ValueError("Chat 模型配置必须完整")
        self._config = config
        self._client = httpx.AsyncClient(timeout=config.timeout)
        self._tools = []

    # 绑定服务端 Tool 定义，模型只能从白名单中选择。
    def bind_tools(self, tools: Sequence[Mapping[str, Any]]) -> "AsyncOpenAIChatModel":
        self._tools = list(tools)
        return self

    # 异步执行一次模型决策。
    async def ainvoke(self, messages: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        response = await self._client.post(self._config.base_url.rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + self._config.api_key}, json={"model": self._config.model, "messages": list(messages), "tools": self._tools or None, "max_tokens": self._config.max_tokens, "stream": False})
        response.raise_for_status()
        return response.json().get("choices", [{}])[0].get("message", {})

    # 异步流式生成最终回答文本块。
    async def astream(self, messages: Sequence[Mapping[str, Any]]) -> AsyncIterator[str]:
        async with self._client.stream("POST", self._config.base_url.rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + self._config.api_key}, json={"model": self._config.model, "messages": list(messages), "max_tokens": self._config.max_tokens, "stream": True}) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    payload = __import__("json").loads(line[6:])
                    content = payload.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content:
                        yield content

    # 关闭异步 HTTP 连接池。
    async def aclose(self) -> None:
        await self._client.aclose()
