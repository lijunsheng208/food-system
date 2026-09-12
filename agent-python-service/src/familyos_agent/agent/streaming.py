"""D2 LangGraph 事件流和请求级超时适配。"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Mapping, Optional


@dataclass(frozen=True)
class AgentEvent:
    """描述对上层 Chat 传输稳定的 Agent 运行事件。"""

    type: str
    content: str = ""
    name: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    """从 LangChain 内容块或普通文本中提取可发送文本。"""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return str(value.get("text", value.get("content", "")) or "")
    return str(value or "")


def _map_event(event: Mapping[str, Any]) -> Optional[AgentEvent]:
    """将 LangGraph v2 原始事件转换为应用层事件，忽略内部噪声事件。"""
    kind = str(event.get("event", ""))
    name = str(event.get("name", ""))
    data = event.get("data") or {}
    if kind == "on_chat_model_stream":
        chunk = data.get("chunk") if isinstance(data, Mapping) else None
        content = _text(getattr(chunk, "content", chunk.get("content", "") if isinstance(chunk, Mapping) else chunk))
        return AgentEvent("model_token", content, name, data) if content else None
    if kind == "on_tool_start":
        return AgentEvent("tool_start", name=name, data=data)
    if kind == "on_tool_end":
        output = data.get("output") if isinstance(data, Mapping) else data
        return AgentEvent("tool_end", _text(output), name, data)
    if kind == "on_chain_start":
        return AgentEvent("node_start", name=name, data=data)
    if kind == "on_chain_end":
        output = data.get("output") if isinstance(data, Mapping) else None
        if isinstance(output, Mapping) and output.get("answer"):
            return AgentEvent("model_token", str(output["answer"]), name, data)
        if isinstance(output, Mapping) and output.get("citations"):
            return AgentEvent("citations", name=name, data={"citations": output.get("citations")})
        return AgentEvent("node_end", name=name, data=data)
    if kind in ("on_tool_error", "on_chain_error", "on_chat_model_error"):
        error = data.get("error") if isinstance(data, Mapping) else data
        return AgentEvent("error", "Agent 节点执行失败", name, {"error": str(error)[:500]})
    return None


async def stream_agent_events(graph: Any, state: Mapping[str, Any], config: Optional[Mapping[str, Any]] = None, total_timeout: float = 60.0) -> AsyncIterator[AgentEvent]:
    """消费 LangGraph v2 事件流，并在总超时或取消时停止当前运行。"""
    if graph is None or total_timeout <= 0:
        raise ValueError("Agent 事件流配置无效")
    if not hasattr(graph, "astream_events"):
        raise TypeError("Graph 不支持 LangGraph 事件流")

    async def consume() -> AsyncIterator[AgentEvent]:
        """读取底层事件并转换为应用事件。"""
        async for raw in graph.astream_events(dict(state), config=dict(config or {}), version="v2"):
            mapped = _map_event(raw)
            if mapped is not None:
                yield mapped

    iterator = consume()
    task = asyncio.create_task(iterator.__anext__())
    deadline = time.monotonic() + total_timeout
    try:
        while True:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    task.cancel()
                    raise TimeoutError("Agent 请求超过总超时时间")
                event = await asyncio.wait_for(task, timeout=remaining)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError as exc:
                task.cancel()
                raise TimeoutError("Agent 请求超过总超时时间") from exc
            yield event
            task = asyncio.create_task(iterator.__anext__())
    except asyncio.CancelledError:
        task.cancel()
        raise
