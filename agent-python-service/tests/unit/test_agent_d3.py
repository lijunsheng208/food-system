import asyncio
import unittest

from familyos_agent.agent import AgentTool, ToolRegistry, build_agent_graph


class FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class InterruptThenAnswerModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return FakeResponse(tool_calls=[{"id": "ask-1", "function": {"name": "ask_user", "arguments": '{"question":"需要几位用餐？","field":"servings"}'}}])
        return FakeResponse("已按人数完成推荐")


class AgentD3Test(unittest.TestCase):
    def test_interrupt_resume_keeps_constraints_and_thread(self):
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.types import Command

        graph = build_agent_graph(
            InterruptThenAnswerModel(),
            ToolRegistry({"lookup": AgentTool("lookup", "查询资料", lambda state, args: "ok")}),
            checkpointer=MemorySaver(),
        )
        config = {"configurable": {"thread_id": "d3-thread"}}
        first = asyncio.run(graph.ainvoke({"original_query": "推荐晚餐", "messages": []}, config=config))
        self.assertEqual(first["terminal_status"], "awaiting_input")
        self.assertEqual(first["pending_question"]["field"], "servings")

        resumed = asyncio.run(graph.ainvoke(Command(resume={"answer": "4", "servings": 4}), config=config))
        self.assertEqual(resumed["terminal_status"], "completed")
        self.assertEqual(resumed["user_constraints"]["servings"], 4)
        self.assertTrue(any("4" in str(getattr(message, "content", message)) for message in resumed["messages"]))


if __name__ == "__main__":
    unittest.main()
