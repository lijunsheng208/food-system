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


class ControlledRetriever:
    """记录受控检索收到的查询文本，验证改写结果进入检索链路。"""

    # retrieve 返回空结果，避免测试依赖 Milvus 或其他外部服务。
    def retrieve(self, query, user_id, knowledge_base_id, index_version=0, top_k=5, strategy=None, plan=None):
        self.query = query
        return {"documents": [], "retrieval_plan": None, "route_strategy": "vector", "fallback_reason": ""}


class QueryRewriteTest(unittest.TestCase):
    """验证 Query Rewrite 开关和结果注入。"""

    def test_rewrites_before_agent_decision(self):
        chat = ChatModel()
        graph = build_agent_graph(chat, ToolRegistry({"noop": AgentTool("noop", "占位工具", lambda state, args: "ok")}), enable_query_rewrite=True, rewrite_model=RewriteModel())
        result = asyncio.run(graph.ainvoke({"original_query": "这个怎么做？", "messages": []}))
        self.assertEqual(result["rewritten_query"], "咖喱炒蟹怎么做？")
        self.assertTrue(any(message.get("role") == "user" and "咖喱炒蟹怎么做？" in message.get("content", "") for message in chat.messages if isinstance(message, dict)))

    def test_rewritten_query_is_used_for_retrieval(self):
        chat = ChatModel()
        retriever = ControlledRetriever()
        graph = build_agent_graph(
            chat,
            ToolRegistry({"noop": AgentTool("noop", "占位工具", lambda state, args: "ok")}),
            enable_query_rewrite=True,
            rewrite_model=RewriteModel(),
            controlled_retriever=retriever,
        )

        asyncio.run(graph.ainvoke({"original_query": "这个怎么做？", "messages": [], "user_id": 1, "knowledge_base_id": 2}))

        self.assertEqual(retriever.query, "咖喱炒蟹怎么做？")


if __name__ == "__main__":
    unittest.main()
