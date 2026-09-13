import asyncio
import unittest

from familyos_agent.agent import AgentTool, ToolRegistry, build_agent_graph


class RewriteModel:
    """返回固定 JSON 的查询改写模型。"""

    async def ainvoke(self, messages):
        return {"content": '{"standalone_query":"咖喱炒蟹怎么做？"}'}


class ChatModel:
    """记录改写后的 Agent 输入并直接结束。"""

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.messages = messages
        return {"content": "完成"}


class QueryRewriteTest(unittest.TestCase):
    """验证 Query Rewrite 开关和结果注入。"""

    def test_rewrites_before_agent_decision(self):
        chat = ChatModel()
        graph = build_agent_graph(chat, ToolRegistry({"noop": AgentTool("noop", "占位工具", lambda state, args: "ok")}), enable_query_rewrite=True, rewrite_model=RewriteModel())
        result = asyncio.run(graph.ainvoke({"original_query": "这个怎么做？", "messages": []}))
        self.assertEqual(result["rewritten_query"], "咖喱炒蟹怎么做？")
        self.assertIn("咖喱炒蟹怎么做？", chat.messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
