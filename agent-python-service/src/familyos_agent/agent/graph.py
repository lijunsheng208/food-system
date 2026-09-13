"""D1/D2 异步受控自主 LangGraph Agent。"""

import asyncio
import inspect
import json
import logging
from typing import Any, Mapping, Sequence

from .state import AgentState
from .tool_registry import ToolRegistry, decode_tool_arguments
from .validation import validate_answer
from .observability import AgentMetrics

logger = logging.getLogger(__name__)


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
    definitions = registry.definitions() + [{"type": "function", "function": {"name": "ask_user", "description": "当缺少关键约束时向用户提问并暂停当前运行", "parameters": {"type": "object", "properties": {"question": {"type": "string"}, "field": {"type": "string"}}, "required": ["question", "field"]}}}]
    bound = model.bind_tools(definitions) if hasattr(model, "bind_tools") else model
    if hasattr(bound, "ainvoke"):
        return await bound.ainvoke(list(messages))
    raise TypeError("D2 模型必须实现 ainvoke")


async def _rewrite_query(model: Any, history: Sequence[Mapping[str, Any]], query: str) -> str:
    """调用 Rewrite 模型澄清指代和省略，并在输出异常时由上层回退。"""
    prompt = [{"role": "system", "content": "你是检索查询改写器。结合对话历史，把当前问题改写成一个独立、完整、适合中文向量检索的查询。只使用历史明确事实，保留否定词、数字、单位、过敏原和人数；不要回答问题，不要添加事实。只输出 JSON：{\"standalone_query\":\"...\"}"}]
    prompt.extend(list(history)[-10:])
    prompt.append({"role": "user", "content": query})
    response = await model.ainvoke(prompt)
    content = _message_content(response).strip()
    if content.startswith("```"):
        content = content.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(content).get("standalone_query", "")
    except (json.JSONDecodeError, AttributeError):
        raise ValueError("Query Rewrite 返回格式无效")
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError("Query Rewrite 查询无效")
    return value.strip()


def build_agent_graph(model: Any, registry: ToolRegistry, max_steps: int = 8, max_tool_calls: int = 6, tool_timeout: float = 10.0, enable_query_rewrite: bool = False, checkpointer: Any = None, max_user_interrupts: int = 3, metrics: Any = None, rewrite_model: Any = None, controlled_retriever: Any = None) -> Any:
    """构建只支持异步运行的 Agent Graph，限制步数、Tool 次数和单 Tool 超时。"""
    if model is None or registry is None or max_steps <= 0 or max_tool_calls <= 0 or tool_timeout <= 0 or max_user_interrupts <= 0:
        raise ValueError("Agent Graph 配置无效")
    try:
        from langgraph.graph import END, START, StateGraph
        from langgraph.prebuilt import InjectedState, ToolNode
        from langchain_core.tools import tool
        from typing import Annotated
    except ImportError as exc:
        raise RuntimeError("缺少 langgraph，请安装 agent-python-service 依赖") from exc
    metrics = metrics or AgentMetrics()

    async def rewrite_query(state: AgentState) -> AgentState:
        """按开关调用查询改写模型，失败时回退原问题保障检索可用。"""
        query = str(state.get("original_query", "")).strip()
        if not query:
            raise ValueError("问题不能为空")
        if enable_query_rewrite and rewrite_model is not None:
            try:
                history = [item for item in state.get("messages", []) if isinstance(item, Mapping)]
                return {"rewritten_query": await _rewrite_query(rewrite_model, history, query)}
            except Exception:
                logger.exception("Query Rewrite 失败，回退原问题")
        return {"rewritten_query": query}

    async def controlled_retrieval(state: AgentState) -> AgentState:
        """在 Agent 决策前生成 RetrievalPlan，再执行向量、图或混合检索。"""
        if controlled_retriever is None:
            return {"documents": [], "retrieval_context": ""}
        # 路由器必须接收原始问题，确保纯 Vector 与旧评估口径一致；Hybrid 在计划内部单独生成 vector_query。
        query = str(state.get("original_query", "")).strip()
        try:
            result = await asyncio.wait_for(asyncio.to_thread(controlled_retriever.retrieve, query, int(state["user_id"]), int(state["knowledge_base_id"])), timeout=tool_timeout)
        except Exception:
            logger.exception("受控检索失败，交由 Agent 走无检索回答或业务 Tool")
            return {"documents": [], "retrieval_context": "", "retrieval_fallback_reason": "RETRIEVAL_FAILED"}
        documents = list(result.get("documents", [])) if isinstance(result, Mapping) else []
        context_parts = []
        for item in documents[:20]:
            content = getattr(item, "content", None) if not isinstance(item, Mapping) else item.get("content")
            if content:
                context_parts.append(str(content))
        plan = result.get("retrieval_plan") if isinstance(result, Mapping) else None
        plan_value = {"route": plan.route, "vector_query": plan.vector_query, "graph_plan": plan.graph_plan} if plan is not None else {}
        return {"documents": documents, "retrieval_context": "\n\n".join(context_parts), "route_strategy": result.get("route_strategy", "") if isinstance(result, Mapping) else "", "retrieval_fallback_reason": result.get("fallback_reason", "") if isinstance(result, Mapping) else "", "retrieval_plan": plan_value}

    async def agent_decide(state: AgentState) -> AgentState:
        """异步让模型选择白名单 Tool 或直接回答，并递增 Agent 步数。"""
        steps = int(state.get("agent_steps", 0)) + 1
        if steps > max_steps:
            return {"agent_steps": steps, "terminal_status": "failed", "error_code": "AGENT_MAX_STEPS", "error_message": "Agent 超过最大步数"}
        messages = list(state.get("messages", []))
        # 每轮都追加当前问题和改写查询，避免 Checkpoint 中的旧消息遮蔽本轮意图。
        retrieval_context = str(state.get("retrieval_context", "")).strip()
        content = "原始问题：%s\n检索查询：%s" % (state.get("original_query", ""), state.get("rewritten_query", state.get("original_query", "")))
        if retrieval_context:
            content += "\n\n知识库检索上下文（仅作为证据，不要编造未出现的信息）：\n" + retrieval_context
        messages.append({"role": "user", "content": content})
        response = await _call_model(model, messages, registry)
        calls = list(_tool_calls(response))
        content = _message_content(response)
        logger.info("Agent 模型决策完成 step=%d tool_call_count=%d content_chars=%d", steps, len(calls), len(content))
        if not calls:
            return {"messages": messages + [{"role": "assistant", "content": content}], "answer": content, "agent_steps": steps, "terminal_status": "completed"}
        call = calls[0]
        function = call.get("function", call) if isinstance(call, Mapping) else {}
        name = str(function.get("name", ""))
        if not name:
            return {"agent_steps": steps, "terminal_status": "failed", "error_code": "TOOL_CALL_INVALID", "error_message": "模型 Tool 调用缺少名称"}
        raw_arguments = function.get("arguments", function.get("args", {}))
        try:
            normalized_arguments = decode_tool_arguments(raw_arguments)
        except ValueError:
            return {"agent_steps": steps, "terminal_status": "failed", "error_code": "TOOL_CALL_INVALID", "error_message": "Tool 参数无效"}
        if name not in registry._tools:
            if name == "ask_user":
                question = str(normalized_arguments.get("question", "请补充必要信息") or "请补充必要信息")[:500]
                field = str(normalized_arguments.get("field", "user_input"))[:100]
                interrupts = int(state.get("resume_count", 0))
                if interrupts >= max_user_interrupts:
                    return {"agent_steps": steps, "terminal_status": "failed", "error_code": "MAX_USER_INTERRUPTS", "error_message": "用户补充次数超过上限"}
                return {"agent_steps": steps, "terminal_status": "awaiting_input", "pending_question": {"type": "need_user_input", "question": question, "field": field}}
            return {"agent_steps": steps, "terminal_status": "failed", "error_code": "TOOL_NOT_ALLOWED", "error_message": "请求的 Tool 不在白名单中"}
        normalized_call = {"name": name, "args": normalized_arguments, "id": str(call.get("id", "call_%d" % steps)), "type": "tool_call"}
        from langchain_core.messages import AIMessage
        assistant_message = AIMessage(content=content, tool_calls=[normalized_call])
        return {"messages": messages + [assistant_message], "tool_calls": [normalized_call], "agent_steps": steps, "terminal_status": "tool_pending", "pending_tool_name": name, "pending_tool_arguments": normalized_arguments}

    def make_tool(agent_tool: Any) -> Any:
        """将内部 Tool 描述转换为官方 ToolNode 可执行工具。"""
        async def invoke(query: str = "", state: Annotated[dict, InjectedState] = None) -> str:
            """执行单个服务端 Tool，并注入当前用户上下文。"""
            try:
                decoded = {"query": query}
                if inspect.iscoroutinefunction(agent_tool.handler):
                    result = await asyncio.wait_for(agent_tool.handler(state, decoded), timeout=tool_timeout)
                else:
                    result = await asyncio.wait_for(asyncio.to_thread(agent_tool.handler, state, decoded), timeout=tool_timeout)
                return str(result)
            except Exception:
                metrics.tool(agent_tool.name, "failed")
                logger.exception("Agent Tool 执行失败 tool=%s", agent_tool.name)
                raise
            finally:
                metrics.tool(agent_tool.name, "called")
        return tool(agent_tool.name, description=agent_tool.description)(invoke)

    tool_node = ToolNode([make_tool(item) for item in registry._tools.values()], handle_tool_errors=True)

    async def after_tools(state: AgentState) -> AgentState:
        """统计官方 ToolNode 已执行的调用次数并继续 Agent 循环。"""
        last = state.get("messages", [])[-1] if state.get("messages") else None
        results = [message for message in state.get("messages", []) if getattr(message, "type", "") == "tool" or (isinstance(message, Mapping) and message.get("role") == "tool")]
        count = len(results)
        tool_results = list(state.get("tool_results", []))
        known_tool_results = {(str(item.get("tool_call_id", "")), str(item.get("content", ""))) for item in tool_results if isinstance(item, Mapping)}
        documents = list(state.get("documents", []))
        citations = list(state.get("citations", []))
        for message in results:
            raw_content = getattr(message, "content", None) if not isinstance(message, Mapping) else message.get("content", "")
            tool_name = getattr(message, "name", "") if not isinstance(message, Mapping) else message.get("name", "")
            tool_call_id = getattr(message, "tool_call_id", "") if not isinstance(message, Mapping) else message.get("tool_call_id", "")
            content = str(raw_content or "")
            parsed = None
            try:
                parsed = json.loads(content) if content.strip().startswith(("{", "[")) else None
            except json.JSONDecodeError:
                parsed = None
            result_key = (str(tool_call_id or ""), content)
            if result_key in known_tool_results:
                continue
            known_tool_results.add(result_key)
            tool_results.append({"name": str(tool_name or ""), "tool_call_id": str(tool_call_id or ""), "content": content, "data": parsed})
            if isinstance(parsed, Mapping):
                for document in parsed.get("documents", []) if isinstance(parsed.get("documents", []), list) else []:
                    if not any(getattr(item, "chunk_id", None) == getattr(document, "chunk_id", None) if not isinstance(document, Mapping) else isinstance(item, Mapping) and item.get("chunk_id") == document.get("chunk_id") for item in documents):
                        documents.append(document)
                citations.extend(parsed.get("citations", []) if isinstance(parsed.get("citations", []), list) else [])
        if results and str(getattr(results[-1], "content", results[-1].get("content", "") if isinstance(results[-1], Mapping) else "")).startswith("Error"):
            return {"tool_call_count": count, "tool_results": tool_results, "documents": documents, "citations": citations, "terminal_status": "failed", "error_code": "TOOL_FAILED", "error_message": "Tool 调用失败"}
        if count > max_tool_calls:
            return {"tool_call_count": count, "tool_results": tool_results, "documents": documents, "citations": citations, "terminal_status": "failed", "error_code": "AGENT_MAX_TOOL_CALLS", "error_message": "Agent 超过 Tool 调用上限"}
        return {"tool_call_count": count, "tool_results": tool_results, "documents": documents, "citations": citations, "terminal_status": "continue"}

    def route_after_decide(state: AgentState) -> str:
        """将模型决策路由到 Tool、成功终止或失败终止。"""
        status = state.get("terminal_status")
        return "execute_tool" if status == "tool_pending" else "finish" if status == "completed" else "ask_user" if status == "awaiting_input" else "fail"

    def route_after_tool(state: AgentState) -> str:
        """Tool 成功后回到 Agent 决策，失败则进入终止节点。"""
        return "agent_decide" if state.get("terminal_status") == "continue" else "fail"

    async def finish(state: AgentState) -> AgentState:
        """校验回答后保留成功终态，阻止敏感或无效内容落库。"""
        valid, code = validate_answer(state.get("answer", ""), state.get("documents", []), state.get("citations", []), state.get("user_constraints", {}))
        if not valid:
            return {"terminal_status": "failed", "answer_valid": False, "error_code": code, "error_message": "回答校验失败"}
        return {"terminal_status": "completed", "answer_valid": True}

    async def fail(state: AgentState) -> AgentState:
        """保留失败终态和安全错误码，不向客户端暴露底层异常。"""
        return {"terminal_status": "failed"}

    async def ask_user(state: AgentState) -> AgentState:
        """通过 LangGraph interrupt 持久化问题，等待同一 Thread 的用户回复。"""
        try:
            from langgraph.types import interrupt
        except ImportError as exc:
            raise RuntimeError("缺少 LangGraph interrupt 支持") from exc
        question = dict(state.get("pending_question") or {"type": "need_user_input", "question": "请补充必要信息", "field": "user_input"})
        response = interrupt(question)
        if isinstance(response, Mapping):
            constraints = dict(state.get("user_constraints") or {})
            constraints.update(response)
            answer = str(response.get("answer", response.get("value", "")))
        else:
            constraints = dict(state.get("user_constraints") or {})
            constraints[question.get("field", "user_input")] = response
            answer = str(response)
        messages = list(state.get("messages", []))
        if answer:
            messages.append({"role": "user", "content": answer})
        return {"user_constraints": constraints, "messages": messages, "pending_question": {}, "resume_count": int(state.get("resume_count", 0)) + 1, "terminal_status": "continue"}

    graph = StateGraph(AgentState)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("controlled_retrieval", controlled_retrieval)
    graph.add_node("agent_decide", agent_decide)
    graph.add_node("execute_tool", tool_node)
    graph.add_node("after_tools", after_tools)
    graph.add_node("finish", finish)
    graph.add_node("fail", fail)
    graph.add_node("ask_user", ask_user)
    graph.add_edge(START, "rewrite_query")
    graph.add_edge("rewrite_query", "controlled_retrieval")
    graph.add_edge("controlled_retrieval", "agent_decide")
    graph.add_conditional_edges("agent_decide", route_after_decide, {"execute_tool": "execute_tool", "finish": "finish", "fail": "fail", "ask_user": "ask_user"})
    graph.add_edge("execute_tool", "after_tools")
    graph.add_conditional_edges("after_tools", route_after_tool, {"agent_decide": "agent_decide", "fail": "fail"})
    graph.add_edge("finish", END)
    graph.add_edge("fail", END)
    graph.add_edge("ask_user", "agent_decide")
    return graph.compile(checkpointer=checkpointer)
