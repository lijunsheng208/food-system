"""验证消息配对、工具预算和会话轮次边界。"""

import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from familyos_agent.agent import AgentTool, ToolRegistry, build_agent_graph
from familyos_agent.transport.grpc.chat import ChatStreamService


class RecordingModel:
    """按顺序返回决策，并保留每次完整的模型输入。"""

    def __init__(self, responses):
        """保存预设响应和输入记录。"""
        self.responses = iter(responses)
        self.inputs = []

    def bind_tools(self, tools):
        """复用当前模型模拟工具绑定。"""
        return self

    async def ainvoke(self, messages):
        """记录提示词与历史后返回下一次决策。"""
        self.inputs.append(messages)
        return next(self.responses)


def tool_call(identifier, name="lookup", arguments=None):
    """构造带稳定调用 ID 的工具请求。"""
    return AIMessage(content="", tool_calls=[{"id": identifier, "name": name, "args": arguments or {}}])


class MessageStateTest(unittest.IsolatedAsyncioTestCase):
    """通过真实编译图覆盖工具循环和 Checkpoint 恢复。"""

    async def test_two_tools_preserve_pairs_and_single_user_message(self):
        """连续工具调用保留历史及配对消息，并准确累计两次执行。"""
        model = RecordingModel([tool_call("t1"), tool_call("t2"), AIMessage(content="完成")])
        graph = build_agent_graph(model, ToolRegistry({"lookup": AgentTool("lookup", "查询", lambda state, args: "结果")}))
        result = await graph.ainvoke({"original_query": "当前问题", "messages": [HumanMessage(content="历史问题"), AIMessage(content="历史回答")]})
        self.assertEqual(result["tool_call_count"], 2)
        self.assertEqual(len(result["tool_results"]), 2)
        self.assertEqual([m.type for m in result["messages"]], ["human", "ai", "human", "ai", "tool", "ai", "tool", "ai"])
        self.assertEqual([m.content for m in result["messages"] if isinstance(m, HumanMessage)], ["历史问题", "当前问题"])
        for messages in model.inputs:
            calls = {call["id"] for m in messages if isinstance(m, AIMessage) for call in m.tool_calls}
            self.assertTrue(all(m.tool_call_id in calls for m in messages if isinstance(m, ToolMessage)))
        self.assertEqual([len(messages) for messages in model.inputs], [4, 6, 8])

    async def test_budget_blocks_extra_tool_before_side_effect(self):
        """耗尽预算后仍可模型决策，但不得执行额外工具。"""
        executed = []
        model = RecordingModel([tool_call("t1"), tool_call("t2")])
        graph = build_agent_graph(model, ToolRegistry({"lookup": AgentTool("lookup", "查询", lambda state, args: executed.append(True) or "结果")}), max_tool_calls=1)
        result = await graph.ainvoke({"original_query": "问题"})
        self.assertEqual(result["error_code"], "AGENT_MAX_TOOL_CALLS")
        self.assertEqual(result["tool_call_count"], 1)
        self.assertEqual(executed, [True])

    async def test_new_turn_resets_execution_but_keeps_history(self):
        """同会话新问题重置计数、引用和约束，保留已有对话。"""
        model = RecordingModel([tool_call("t1"), AIMessage(content="第一轮完成"), tool_call("t2"), AIMessage(content="第二轮完成")])
        registry = ToolRegistry({"lookup": AgentTool("lookup", "查询", lambda state, args: "结果")})
        graph = build_agent_graph(model, registry, max_steps=2, max_tool_calls=1, checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "two-turns"}}
        await graph.ainvoke({"original_query": "第一问", "request_id": "r1"}, config)
        await graph.aupdate_state(config, {"citations": [{"chunk_id": "old"}], "user_constraints": {"servings": 9}, "resume_count": 3})
        result = await graph.ainvoke({"original_query": "第二问", "request_id": "r2"}, config)
        self.assertEqual(result["terminal_status"], "completed")
        self.assertEqual(result["agent_steps"], 2)
        self.assertEqual(result["tool_call_count"], 1)
        self.assertEqual(len(result["tool_results"]), 1)
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["user_constraints"], {})
        self.assertEqual(result["resume_count"], 0)
        self.assertEqual([m.content for m in result["messages"] if isinstance(m, HumanMessage)], ["第一问", "第二问"])

    async def test_resume_preserves_tool_budget_and_constraints(self):
        """暂停恢复保留工具结果和预算，继续消费原轮次而非重新初始化。"""
        model = RecordingModel([tool_call("t1"), tool_call("ask", "ask_user", {"question": "几人份？", "field": "servings"}), tool_call("t2")])
        graph = build_agent_graph(model, ToolRegistry({"lookup": AgentTool("lookup", "查询", lambda state, args: "结果")}), max_tool_calls=1, checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "resume"}}
        first = await graph.ainvoke({"original_query": "推荐晚餐"}, config)
        self.assertEqual(first["terminal_status"], "awaiting_input")
        result = await graph.ainvoke(Command(resume={"answer": "三人", "servings": 3}), config)
        self.assertEqual(result["error_code"], "AGENT_MAX_TOOL_CALLS")
        self.assertEqual(result["tool_call_count"], 1)
        self.assertEqual(result["agent_steps"], 3)
        self.assertEqual(result["resume_count"], 1)
        self.assertEqual(result["user_constraints"]["servings"], 3)
        self.assertEqual(len(result["tool_results"]), 1)
        self.assertEqual([m.content for m in result["messages"] if isinstance(m, HumanMessage)], ["推荐晚餐", "三人"])

    async def test_service_replaces_checkpoint_history_with_database_context(self):
        """数据库历史替换旧 Checkpoint，避免 reducer 合并出重复或过期历史。"""
        class Conversations:
            """提供已经压缩后的消息表历史。"""

            def begin_chat(self, request):
                """模拟已校验的请求入库。"""
                return None

            def get_chat_context(self, conversation_id, request_id):
                """返回当前数据库保留的历史。"""
                return {"messages": [{"role": "user", "content": "第一问"}, {"role": "assistant", "content": "第一答"}]}

            def complete_chat(self, request_id, content, citations):
                """模拟回答成功落库。"""
                return None

        model = RecordingModel([AIMessage(content="第一答"), AIMessage(content="第二答")])
        graph = build_agent_graph(model, ToolRegistry({"lookup": AgentTool("lookup", "查询", lambda state, args: "结果")}), checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "service"}}
        await graph.ainvoke({"original_query": "第一问"}, config)
        service = ChatStreamService(graph, "token", conversations=Conversations(), context_model=model)
        events = [event async for event in service.stream({"conversation_id": "service", "request_id": "r2", "message": "第二问", "original_query": "第二问"})]
        self.assertEqual(events[-1].type, "completed")
        snapshot = await graph.aget_state(config)
        self.assertEqual([m.content for m in snapshot.values["messages"]], ["第一问", "第一答", "第二问", "第二答"])
