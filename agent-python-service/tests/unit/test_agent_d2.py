import asyncio
import unittest

from familyos_agent.agent import stream_agent_events
from familyos_agent.transport.grpc.chat import ChatStreamService


class FakeGraph:
    async def astream_events(self, state, config, version):
        yield {"event": "on_chain_start", "name": "agent_decide", "data": {}}
        yield {"event": "on_tool_start", "name": "lookup", "data": {}}
        yield {"event": "on_tool_end", "name": "lookup", "data": {"output": "结果"}}
        yield {"event": "on_chat_model_stream", "name": "model", "data": {"chunk": {"content": "回答"}}}
        yield {"event": "on_chain_end", "name": "finish", "data": {}}


class AgentD2Test(unittest.TestCase):
    def test_maps_langgraph_v2_events(self):
        async def run():
            return [event async for event in stream_agent_events(FakeGraph(), {"original_query": "问题"})]
        events = asyncio.run(run())
        self.assertEqual([event.type for event in events], ["node_start", "tool_start", "tool_end", "model_token", "node_end"])
        self.assertEqual(events[3].content, "回答")

    def test_maps_events_to_chat_proto(self):
        async def run():
            service = ChatStreamService(FakeGraph(), "token")
            return [event async for event in service.stream({"request_id": "r1", "conversation_id": "c1"})]
        events = asyncio.run(run())
        self.assertEqual([event.type for event in events], ["tool_start", "tool_end", "answer_delta", "completed"])
        self.assertEqual(events[2].content, "回答")


if __name__ == "__main__":
    unittest.main()
