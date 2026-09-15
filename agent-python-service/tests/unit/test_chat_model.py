import asyncio
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from familyos_agent.agent import AgentTool, ToolRegistry, build_agent_graph
from familyos_agent.clients.chat_model import AsyncOpenAIChatModel
from familyos_agent.config import ChatConfig
from familyos_agent.transport.grpc.chat import ChatStreamService


class FakeStreamResponse:
    """模拟 httpx 流式响应并按顺序返回 SSE 行。"""

    def __init__(self, lines):
        """保存本次响应要输出的 SSE 行。"""
        self.status_code = 200
        self._lines = lines

    async def __aenter__(self):
        """进入异步流式响应上下文。"""
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        """退出异步流式响应上下文。"""
        return False

    def raise_for_status(self):
        """模拟成功响应，不抛出 HTTP 异常。"""
        return None

    async def aiter_lines(self):
        """逐行输出预设 SSE 内容。"""
        for line in self._lines:
            yield line


class FakeJSONResponse:
    """模拟 httpx 非流式 JSON 响应。"""

    def __init__(self, body):
        """保存返回给模型客户端的响应体。"""
        self.status_code = 200
        self._body = body

    def raise_for_status(self):
        """模拟成功响应，不抛出 HTTP 异常。"""
        return None

    def json(self):
        """返回预设 JSON 响应体。"""
        return self._body


class FakeAsyncClient:
    """记录模型请求并为多轮 Agent 调用提供预设流。"""

    def __init__(self, streams=(), responses=()):
        """保存每次流式与非流式模型调用对应的预设响应。"""
        self._streams = list(streams)
        self._responses = list(responses)
        self.payloads = []

    async def __aenter__(self):
        """进入异步 HTTP 客户端上下文。"""
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        """退出异步 HTTP 客户端上下文。"""
        return False

    def stream(self, method, url, headers, json):
        """记录请求体并返回下一组流式响应。"""
        self.payloads.append(json)
        return FakeStreamResponse(self._streams.pop(0))

    async def post(self, url, headers, json):
        """记录请求体并返回下一份非流式 JSON 响应。"""
        self.payloads.append(json)
        return FakeJSONResponse(self._responses.pop(0))


def make_config() -> ChatConfig:
    """构造不访问真实网络的最小 Chat 配置。"""
    return ChatConfig(50054, "token", 1, "https://example.com/v1", "secret", "qwen", 10.0, 256, 3, 2)


def sse(payload) -> str:
    """把字典编码为 OpenAI-compatible SSE 数据行。"""
    return "data: " + json.dumps(payload, ensure_ascii=False)


class ChatModelStreamingTest(unittest.TestCase):
    """验证 ChatModel 的文本和 Tool Call 流式协议。"""

    def test_streaming_tool_call_chunks_are_aggregated(self):
        """验证分片的 Tool 名称和 JSON 参数能聚合为标准 Tool Call。"""
        stream = [
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "search_", "arguments": "{\"query\":\"番"}}]}, "finish_reason": None}]}),
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "knowledge_base", "arguments": "茄\"}"}}]}, "finish_reason": "tool_calls"}]}),
            "data: [DONE]",
        ]
        client = FakeAsyncClient([stream])
        model = AsyncOpenAIChatModel(make_config()).bind_tools([{"type": "function", "function": {"name": "search_knowledge_base"}}])

        async def run():
            """消费并合并 LangChain 模型消息块。"""
            chunks = [chunk async for chunk in model.astream([HumanMessage(content="问题")])]
            combined = chunks[0]
            for chunk in chunks[1:]:
                combined += chunk
            return combined

        with patch("familyos_agent.clients.chat_model.httpx.AsyncClient", return_value=client):
            message = asyncio.run(run())

        self.assertTrue(client.payloads[0]["stream"])
        self.assertIn("tools", client.payloads[0])
        self.assertEqual(message.tool_calls[0]["name"], "search_knowledge_base")
        self.assertEqual(message.tool_calls[0]["args"], {"query": "番茄"})

    def test_disabled_streaming_uses_regular_completion(self):
        """验证查询改写模型禁用流式后仍通过普通响应返回完整消息。"""
        client = FakeAsyncClient(responses=[{
            "choices": [{"message": {"content": '{"standalone_query":"番茄炒蛋"}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }])
        model = AsyncOpenAIChatModel(make_config(), enable_streaming=False)

        async def run():
            """调用禁用流式的模型实例。"""
            return await model.ainvoke([HumanMessage(content="这个怎么做")])

        with patch("familyos_agent.clients.chat_model.httpx.AsyncClient", return_value=client):
            message = asyncio.run(run())

        self.assertFalse(client.payloads[0]["stream"])
        self.assertEqual(message.content, '{"standalone_query":"番茄炒蛋"}')
        self.assertEqual(message.usage_metadata["total_tokens"], 15)

    def test_langgraph_streams_answer_after_tool_call(self):
        """验证 LangGraph 聚合 Tool Call 后执行工具，并流式发送第二轮回答。"""
        tool_stream = [
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "lookup", "arguments": "{\"query\":"}}]}, "finish_reason": None}]}),
            sse({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\"菜单\"}"}}]}, "finish_reason": "tool_calls"}]}),
            "data: [DONE]",
        ]
        answer_stream = [
            sse({"choices": [{"delta": {"content": "菜"}, "finish_reason": None}]}),
            sse({"choices": [{"delta": {"content": "谱"}, "finish_reason": "stop"}]}),
            "data: [DONE]",
        ]
        client = FakeAsyncClient([tool_stream, answer_stream])
        tool_queries = []

        def lookup(_state, arguments):
            """记录模型生成的 Tool 参数并返回固定证据。"""
            tool_queries.append(arguments["query"])
            return "检索结果"

        graph = build_agent_graph(
            AsyncOpenAIChatModel(make_config()),
            ToolRegistry({"lookup": AgentTool("lookup", "查询菜单", lookup)}),
            max_steps=3,
            max_tool_calls=2,
        )

        async def run():
            """消费完整 Chat 服务流并返回对外回答增量。"""
            service = ChatStreamService(graph, "token")
            events = [event async for event in service.stream({"request_id": "r1", "conversation_id": "c1", "original_query": "查菜单", "message": "查菜单"})]
            return [event.content for event in events if event.type == "answer_delta"]

        with patch("familyos_agent.clients.chat_model.httpx.AsyncClient", return_value=client):
            tokens = asyncio.run(run())

        self.assertEqual(tool_queries, ["菜单"])
        self.assertEqual(tokens, ["菜", "谱"])
        self.assertEqual(len(client.payloads), 2)
        self.assertTrue(all(payload["stream"] for payload in client.payloads))


if __name__ == "__main__":
    unittest.main()
