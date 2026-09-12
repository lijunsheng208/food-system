"""D1/D2 异步受控自主 LangGraph Agent。"""

import asyncio
import inspect
from typing import Any, Mapping, Sequence

from .state import AgentState
from .tool_registry import ToolRegistry, decode_tool_arguments


def _message_content(message: Any) -> str:
    """从 LangChain Message 或兼容字典中提取文本内容。"""
    content = message.content if hasattr(message, "content") else message.get("content", "") if isinstance(message, dict) else message
    if isinstance(content, list):
        return "".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    return str(content or "")


def _tool_calls(message: Any) -> Sequence[Mapping[str, Any]]:
    """兼容 AIMessage 和 OpenAI-compatible 字典的 Tool Call 表示。"""
    calls = getattr(message, "tool_calls", None)
    if calls is None and isinstance(message, dict):
        calls = message.get("tool_calls") or message.get("additional_kwargs", {}).get("tool_calls")
    return calls or ()


async def _call_model(model: Any, messages: Sequence[Mapping[str, Any]], registry: ToolRegistry) -> Any:
    """调用模型的异步 ainvoke 接口，D2 不再保留同步模型执行路径。"""
    bound = model.bind_tools(registry.definitions()) if hasattr(model, "bind_tools") else model
    if hasattr(bound, "ainvoke"):
        return await bound.ainvoke(list(messages))
    raise TypeError("D2 模型必须实现 ainvoke")


def build_agent_graph(model: Any, registry: ToolRegistry, max_steps: int = 8, max_tool_calls: int = 6, tool_timeout: float = 10.0, enable_query_rewrite: bool = False) -> Any:
    """构建只支持异步运行的 Agent Graph，限制步数、Tool 次数和单 Tool 超时。"""
    if model is None or registry is None or max_steps <= 0 or max_tool_calls <= 0 or tool_timeout <= 0:
        raise ValueError("Agent Graph 配置无效")
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("缺少 langgraph，请安装 agent-python-service 依赖") from exc

    async def rewrite_query(state: AgentState) -> AgentState:
        """D1 默认异步透传原问题，后续 Query Rewrite 可在此替换。"""
        query = str(state.get("original_query", "")).strip()
        if not query:
            raise ValueError("问题不能为空")
        return {"rewritten_query": query}

    async def agent_decide(state: AgentState) -> AgentState:
        """异步让模型选择白名单 Tool 或直接回答，并递增 Agent 步数。"""
        steps = int(state.get("agent_steps", 0)) + 1
        if steps > max_steps:
            return {"agent_steps": steps, "terminal_status": "failed", "error_code": "AGENT_MAX_STEPS", "error_message": "Agent 超过最大步数"}
        messages = list(state.get("messages", [])) or [{"role": "user", "content": state.get("original_query", "")}]
        response = await _call_model(model, messages, registry)
        calls = list(_tool_calls(response))
        content = _message_content(response)
        if not calls:
            return {"messages": messages + [{"role": "assistant", "content": content}], "answer": content, "agent_steps": steps, "terminal_status": "completed"}
        call = calls[0]
        function = call.get("function", call) if isinstance(call, Mapping) else {}
        name = str(function.get("name", ""))
        if not name:
            return {"agent_steps": steps, "terminal_status": "failed", "error_code": "TOOL_CALL_INVALID", "error_message": "模型 Tool 调用缺少名称"}
        return {"messages": messages + [{"role": "assistant", "content": content, "tool_calls": [dict(call)]}], "tool_calls": [dict(call)], "agent_steps": steps, "terminal_status": "tool_pending", "pending_tool_name": name, "pending_tool_arguments": function.get("arguments", {})}

    async def execute_tool(state: AgentState) -> AgentState:
        """异步执行模型选择的白名单 Tool，并将结果写回消息上下文。"""
        count = int(state.get("tool_call_count", 0)) + 1
        if count > max_tool_calls:
            return {"tool_call_count": count, "terminal_status": "failed", "error_code": "AGENT_MAX_TOOL_CALLS", "error_message": "Agent 超过 Tool 调用上限"}
        try:
            tool = registry.get(str(state.get("pending_tool_name", "")))
            arguments = decode_tool_arguments(state.get("pending_tool_arguments", {}))
            if inspect.iscoroutinefunction(tool.handler):
                result = await asyncio.wait_for(tool.handler(state, arguments), timeout=tool_timeout)
            else:
                result = await asyncio.wait_for(asyncio.to_thread(tool.handler, state, arguments), timeout=tool_timeout)
        except KeyError:
            return {"tool_call_count": count, "terminal_status": "failed", "error_code": "TOOL_NOT_ALLOWED", "error_message": "请求的 Tool 不在白名单中"}
        except ValueError:
            return {"tool_call_count": count, "terminal_status": "failed", "error_code": "TOOL_ARGUMENT_INVALID", "error_message": "Tool 参数无效"}
        except asyncio.TimeoutError:
            return {"tool_call_count": count, "terminal_status": "failed", "error_code": "TOOL_TIMEOUT", "error_message": "Tool 调用超时"}
        except Exception:
            return {"tool_call_count": count, "terminal_status": "failed", "error_code": "TOOL_FAILED", "error_message": "Tool 调用失败"}
        name = str(state.get("pending_tool_name", ""))
        return {"messages": list(state.get("messages", [])) + [{"role": "tool", "name": name, "content": str(result)}], "tool_results": list(state.get("tool_results", [])) + [{"name": name, "result": result}], "tool_call_count": count, "terminal_status": "continue"}

    def route_after_decide(state: AgentState) -> str:
        """将模型决策路由到 Tool、成功终止或失败终止。"""
        return "execute_tool" if state.get("terminal_status") == "tool_pending" else "finish" if state.get("terminal_status") == "completed" else "fail"

    def route_after_tool(state: AgentState) -> str:
        """Tool 成功后回到 Agent 决策，失败则进入终止节点。"""
        return "agent_decide" if state.get("terminal_status") == "continue" else "fail"

    async def finish(state: AgentState) -> AgentState:
        """保留成功终态，供事件流和传输层映射完成事件。"""
        return {"terminal_status": "completed"}

    async def fail(state: AgentState) -> AgentState:
        """保留失败终态和安全错误码，不向客户端暴露底层异常。"""
        return {"terminal_status": "failed"}

    graph = StateGraph(AgentState)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("agent_decide", agent_decide)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("finish", finish)
    graph.add_node("fail", fail)
    graph.add_edge(START, "rewrite_query")
    graph.add_edge("rewrite_query", "agent_decide")
    graph.add_conditional_edges("agent_decide", route_after_decide, {"execute_tool": "execute_tool", "finish": "finish", "fail": "fail"})
    graph.add_conditional_edges("execute_tool", route_after_tool, {"agent_decide": "agent_decide", "fail": "fail"})
    graph.add_edge("finish", END)
    graph.add_edge("fail", END)
    return graph.compile()
