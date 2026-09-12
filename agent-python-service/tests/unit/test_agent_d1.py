import asyncio
import unittest

from familyos_agent.agent import AgentTool, ToolRegistry, build_agent_graph


class FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class FakeModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return FakeResponse(tool_calls=[{"id": "1", "function": {"name": "lookup", "arguments": '{"query":"菜单"}'}}])
        return FakeResponse("最终回答")


class AgentD1Test(unittest.TestCase):
    def test_controlled_tool_loop(self):
        registry = ToolRegistry({"lookup": AgentTool("lookup", "查询资料", lambda state, args: {"value": args["query"]})})
        graph = build_agent_graph(FakeModel(), registry, max_steps=3, max_tool_calls=2)
        result = asyncio.run(graph.ainvoke({"original_query": "帮我查菜单", "messages": []}))
        self.assertEqual(result["answer"], "最终回答")
        self.assertEqual(result["tool_call_count"], 1)
        self.assertEqual(result["terminal_status"], "completed")

    def test_unknown_tool_fails_closed(self):
        class UnknownModel:
            def bind_tools(self, tools): return self
            async def ainvoke(self, messages): return FakeResponse(tool_calls=[{"function": {"name": "unknown", "arguments": "{}"}}])
        registry = ToolRegistry({"lookup": AgentTool("lookup", "查询资料", lambda state, args: "ok")})
        result = asyncio.run(build_agent_graph(UnknownModel(), registry).ainvoke({"original_query": "问题", "messages": []}))
        self.assertEqual(result["error_code"], "TOOL_NOT_ALLOWED")
        self.assertEqual(result["terminal_status"], "failed")


if __name__ == "__main__":
    unittest.main()
