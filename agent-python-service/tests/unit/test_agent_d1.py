import asyncio
import json
import unittest

from familyos_agent.agent import AgentTool, ToolRegistry, build_agent_graph


class FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class FakeModel:
    def __init__(self):
        """初始化调用次数和每轮模型输入。"""
        self.calls = 0
        self.messages = []

    def bind_tools(self, tools):
        """模拟绑定 Tool 并保留当前模型。"""
        return self

    async def ainvoke(self, messages):
        """记录输入，首轮调用 Tool，第二轮返回最终回答。"""
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            return FakeResponse(tool_calls=[{"id": "1", "function": {"name": "lookup", "arguments": '{"query":"菜单"}'}}])
        return FakeResponse("最终回答")


class AgentD1Test(unittest.TestCase):
    def test_controlled_tool_loop(self):
        """验证主 Agent 携带系统提示词并完成受控 Tool 循环。"""
        model = FakeModel()
        registry = ToolRegistry({"lookup": AgentTool("lookup", "查询资料", lambda state, args: {"value": args["query"]})})
        graph = build_agent_graph(model, registry, max_steps=3, max_tool_calls=2)
        result = asyncio.run(graph.ainvoke({"original_query": "帮我查菜单", "messages": []}))
        self.assertEqual(result["answer"], "最终回答")
        self.assertEqual(result["tool_call_count"], 1)
        self.assertEqual(result["terminal_status"], "completed")
        self.assertEqual(model.messages[0][0]["role"], "system")
        self.assertIn("FamilyOS 家庭饮食助手", model.messages[0][0]["content"])

    def test_dietary_tool_results_become_hard_constraints(self):
        """验证饮食 Tool 结果进入模型上下文，并将忌口和过敏写入硬约束。"""
        class DietaryModel:
            """首轮查询饮食偏好，第二轮给出符合约束的回答。"""

            def __init__(self):
                """初始化模型调用次数和输入记录。"""
                self.calls = 0
                self.messages = []

            def bind_tools(self, tools):
                """模拟绑定饮食 Tool。"""
                return self

            async def ainvoke(self, messages):
                """先调用饮食 Tool，再基于返回结果回答。"""
                self.calls += 1
                self.messages.append(messages)
                if self.calls == 1:
                    return FakeResponse(tool_calls=[{"id": "diet-1", "function": {"name": "get_user_dietary_preferences", "arguments": "{}"}}])
                return FakeResponse("可以选择清淡的番茄豆腐汤。")

        async def dietary_handler(state, arguments):
            """返回一项忌口和一项过敏食材。"""
            return json.dumps({"preferences": [
                {"preference_type": 4, "preference_value": "辣椒", "preference_type_name": "忌口食材"},
                {"preference_type": 5, "preference_value": "花生", "preference_type_name": "过敏食材"},
            ]}, ensure_ascii=False)

        model = DietaryModel()
        registry = ToolRegistry({
            "get_user_dietary_preferences": AgentTool("get_user_dietary_preferences", "查询饮食偏好", dietary_handler, {"type": "object", "properties": {}}),
        })
        result = asyncio.run(build_agent_graph(model, registry).ainvoke({"original_query": "推荐一道菜", "messages": [], "user_id": 7}))

        self.assertEqual(result["terminal_status"], "completed")
        self.assertEqual(result["user_constraints"]["avoided_ingredients"], ["辣椒"])
        self.assertEqual(result["user_constraints"]["allergens"], ["花生"])
        self.assertIn("get_user_dietary_preferences", model.messages[0][0]["content"])
        self.assertTrue(any("花生" in str(getattr(message, "content", message)) for message in model.messages[1]))

    def test_unknown_tool_fails_closed(self):
        class UnknownModel:
            def bind_tools(self, tools): return self
            async def ainvoke(self, messages): return FakeResponse(tool_calls=[{"function": {"name": "unknown", "arguments": "{}"}}])
        registry = ToolRegistry({"lookup": AgentTool("lookup", "查询资料", lambda state, args: "ok")})
        result = asyncio.run(build_agent_graph(UnknownModel(), registry).ainvoke({"original_query": "问题", "messages": []}))
        self.assertEqual(result["error_code"], "TOOL_NOT_ALLOWED")
        self.assertEqual(result["terminal_status"], "failed")

    def test_tool_results_are_normalized_into_state(self):
        class ToolModel:
            def __init__(self): self.calls = 0
            def bind_tools(self, tools): return self
            async def ainvoke(self, messages):
                self.calls += 1
                if self.calls == 1:
                    return FakeResponse(tool_calls=[{"id": "t1", "function": {"name": "lookup", "arguments": '{"query":"菜单"}'}}])
                return FakeResponse("基于证据的回答")

        registry = ToolRegistry({"lookup": AgentTool("lookup", "查询资料", lambda state, args: '{"documents":[{"chunk_id":"c1","content":"菜单原文"}],"citations":[{"chunk_id":"c1"}]}')})
        result = asyncio.run(build_agent_graph(ToolModel(), registry).ainvoke({"original_query": "查菜单", "messages": []}))
        self.assertEqual(result["tool_results"][0]["tool_call_id"], "t1")
        self.assertEqual(result["documents"][0]["chunk_id"], "c1")
        self.assertEqual(result["citations"][0]["chunk_id"], "c1")


if __name__ == "__main__":
    unittest.main()
