import asyncio
import unittest
from unittest.mock import patch

from familyos_agent.agent import stream_agent_events
from familyos_agent.transport.grpc.chat import ChatStreamService


class FakeGraph:
    """生成一组固定 LangGraph 事件，供流式映射测试使用。"""

    async def astream_events(self, state, config, version):
        """按正常问答顺序异步返回工具和模型事件。"""
        yield {"event": "on_chain_start", "name": "agent_decide", "data": {}}
        yield {"event": "on_tool_start", "name": "lookup", "data": {}}
        yield {"event": "on_tool_end", "name": "lookup", "data": {"output": "结果"}}
        yield {"event": "on_chat_model_stream", "name": "model", "data": {"chunk": {"content": "回答"}}}
        yield {"event": "on_chain_end", "name": "finish", "data": {}}


class FailingGraph:
    """在输出首个事件后抛错，用于验证异常清理。"""

    async def astream_events(self, state, config, version):
        """先输出一个事件，再模拟 Graph 执行失败。"""
        yield {"event": "on_chat_model_stream", "name": "model", "data": {"chunk": {"content": "部分回答"}}}
        raise RuntimeError("graph failed")


class NonStreamingGraph:
    """模拟模型只返回完整终态、不产生 token 流的生产调用方式。"""

    async def astream_events(self, state, config, version):
        """返回已经通过回答校验的最终 Graph 状态。"""
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"answer": "完整回答", "answer_valid": True, "terminal_status": "completed"}},
        }


class StreamingGraph:
    """模拟既有 token 流又包含最终完整状态的模型调用。"""

    async def astream_events(self, state, config, version):
        """先发送 token，再返回包含相同答案的最终 Graph 状态。"""
        yield {"event": "on_chat_model_stream", "name": "model", "data": {"chunk": {"content": "流式回答"}}}
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"answer": "流式回答", "answer_valid": True, "terminal_status": "completed"}},
        }


class AwaitingInputGraph:
    """模拟 LangGraph 暂停并要求用户补充信息。"""

    async def astream_events(self, state, config, version):
        """返回包含待追问内容的等待态 Graph 事件。"""
        yield {
            "event": "on_chain_end",
            "name": "ask_user",
            "data": {
                "output": {
                    "terminal_status": "awaiting_input",
                    "pending_question": {"question": "请问你想做几人份？", "field": "servings"},
                }
            },
        }


class RecordingConversations:
    """记录会话持久化调用，供等待态消息回归测试使用。"""

    def __init__(self):
        """初始化已完成消息调用记录。"""
        self.completed = []
        self.failed = []

    def begin_chat(self, request):
        """模拟创建本轮用户消息和助手占位消息。"""

    def complete_chat(self, request_id, answer, citations):
        """记录助手消息从流式状态转为完成状态的参数。"""
        self.completed.append((request_id, answer, citations))

    def fail_chat(self, request_id, error_code, message):
        """记录助手消息从流式状态转为失败状态的参数。"""
        self.failed.append((request_id, error_code, message))


class ResumeRecordingGraph:
    """记录等待态恢复输入和 Thread 配置。"""

    def __init__(self):
        """初始化收到的 Graph 输入和配置。"""
        self.received_state = None
        self.received_config = None

    def get_state(self, config):
        """模拟同一 Thread 中已有等待用户输入的 Checkpoint。"""
        snapshot = type("CheckpointSnapshot", (), {})()
        snapshot.values = {"terminal_status": "awaiting_input"}
        return snapshot

    async def astream_events(self, state, config, version):
        """记录恢复命令并返回完成态回答。"""
        self.received_state = state
        self.received_config = config
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"answer": "已按三人份继续", "answer_valid": True, "terminal_status": "completed"}},
        }


class ClosableGraph:
    """记录异步事件生成器是否在客户端中断后及时关闭。"""

    def __init__(self):
        """初始化生成器关闭状态。"""
        self.closed = False

    async def astream_events(self, state, config, version):
        """持续产生事件，并在生成器关闭时记录清理完成。"""
        try:
            yield {"event": "on_chat_model_stream", "name": "model", "data": {"chunk": {"content": "第一段"}}}
            yield {"event": "on_chat_model_stream", "name": "model", "data": {"chunk": {"content": "第二段"}}}
        finally:
            self.closed = True


class TimeoutGraph:
    """模拟始终没有下一条事件的 LangGraph 流。"""

    def __init__(self):
        """初始化底层事件流关闭状态。"""
        self.closed = False

    async def astream_events(self, state, config, version):
        """持续等待直到请求超时，并在取消时记录关闭完成。"""
        try:
            await asyncio.Event().wait()
            if False:
                yield {}
        finally:
            self.closed = True


class RecordingSpan:
    """记录 span 结束次数，验证所有流式退出路径都完成清理。"""

    def __init__(self):
        """初始化结束次数。"""
        self.end_count = 0

    def end(self):
        """记录一次显式结束调用。"""
        self.end_count += 1


class AgentD2Test(unittest.TestCase):
    def test_maps_langgraph_v2_events(self):
        """验证 LangGraph v2 事件能映射为内部事件。"""
        async def run():
            """消费内部事件流并返回完整事件列表。"""
            return [event async for event in stream_agent_events(FakeGraph(), {"original_query": "问题"})]
        events = asyncio.run(run())
        self.assertEqual([event.type for event in events], ["node_start", "tool_start", "tool_end", "model_token", "node_end"])
        self.assertEqual(events[3].content, "回答")

    def test_maps_events_to_chat_proto(self):
        """验证内部事件能映射为 Chat Proto 流。"""
        async def run():
            """消费 Chat 服务流并返回完整 Proto 事件列表。"""
            service = ChatStreamService(FakeGraph(), "token")
            return [event async for event in service.stream({"request_id": "r1", "conversation_id": "c1"})]
        events = asyncio.run(run())
        self.assertEqual([event.type for event in events], ["tool_start", "tool_end", "answer_delta", "completed"])
        self.assertEqual(events[2].content, "回答")

    def test_emits_validated_answer_when_model_does_not_stream(self):
        """验证 ainvoke 完整响应会在最终校验后转换为回答事件。"""
        async def run():
            """消费不产生 token 的 Graph 事件流。"""
            service = ChatStreamService(NonStreamingGraph(), "token")
            return [event async for event in service.stream({"request_id": "r1", "conversation_id": "c1"})]

        events = asyncio.run(run())

        self.assertEqual([event.type for event in events], ["answer_delta", "completed"])
        self.assertEqual(events[0].content, "完整回答")

    def test_does_not_repeat_final_answer_after_streamed_tokens(self):
        """验证已有 token 输出时不会再次发送最终完整答案。"""
        async def run():
            """消费同时包含 token 和最终状态的 Graph 事件流。"""
            service = ChatStreamService(StreamingGraph(), "token")
            return [event async for event in service.stream({"request_id": "r1", "conversation_id": "c1"})]

        events = asyncio.run(run())

        self.assertEqual([event.type for event in events], ["answer_delta", "completed"])
        self.assertEqual(events[0].content, "流式回答")

    def test_completes_assistant_message_when_awaiting_input(self):
        """验证追问会发送等待态事件、完成助手消息且不发送 completed 事件。"""
        conversations = RecordingConversations()

        async def run():
            """消费等待用户输入的 Chat 服务流。"""
            service = ChatStreamService(AwaitingInputGraph(), "token", conversations=conversations)
            return [event async for event in service.stream({"request_id": "r1", "conversation_id": "c1"})]

        events = asyncio.run(run())

        self.assertEqual([event.type for event in events], ["awaiting_input"])
        self.assertEqual(events[0].content, "请问你想做几人份？")
        self.assertEqual(conversations.completed, [("r1", "请问你想做几人份？", [])])

    def test_resumes_checkpoint_with_same_conversation_id(self):
        """验证后续消息通过同一 conversation_id 恢复等待态 Checkpoint。"""
        graph = ResumeRecordingGraph()

        async def run():
            """发送用户补充内容并消费恢复后的回答。"""
            service = ChatStreamService(graph, "token")
            return [event async for event in service.stream({"request_id": "r2", "conversation_id": "c1", "message": "三人份"})]

        events = asyncio.run(run())

        self.assertEqual([event.type for event in events], ["answer_delta", "completed"])
        self.assertEqual(getattr(graph.received_state, "resume", None), "三人份")
        self.assertEqual(graph.received_config["configurable"]["thread_id"], "c1")

    def test_closes_graph_generator_when_event_stream_stops_early(self):
        """验证外层停止消费时会关闭底层 LangGraph 异步生成器。"""
        graph = ClosableGraph()

        async def run():
            """消费首个事件后主动关闭应用事件流。"""
            iterator = stream_agent_events(graph, {"original_query": "问题"})
            await iterator.__anext__()
            await iterator.aclose()

        asyncio.run(run())

        self.assertTrue(graph.closed)

    def test_closes_graph_and_fails_chat_when_request_times_out(self):
        """验证总超时会关闭底层 Graph，并将助手占位消息更新为失败。"""
        graph = TimeoutGraph()
        conversations = RecordingConversations()

        async def run():
            """消费不会产生事件的 Chat 流直到触发请求级超时。"""
            service = ChatStreamService(graph, "token", total_timeout=0.01, conversations=conversations)
            return [event async for event in service.stream({"request_id": "timeout-1", "conversation_id": "c1"})]

        with self.assertRaises(TimeoutError):
            asyncio.run(run())

        self.assertTrue(graph.closed)
        self.assertEqual(conversations.failed, [("timeout-1", "MODEL_TIMEOUT", "Agent 请求超时")])

    def test_ends_trace_when_stream_completes(self):
        """验证正常完成时显式结束追踪 span。"""
        span = RecordingSpan()

        async def run():
            """完整消费一次 Chat 服务流。"""
            service = ChatStreamService(FakeGraph(), "token")
            return [event async for event in service.stream({"request_id": "r1", "conversation_id": "c1"})]

        with patch("familyos_agent.transport.grpc.chat.trace_run", return_value=span):
            asyncio.run(run())

        self.assertEqual(span.end_count, 1)

    def test_ends_trace_when_stream_is_closed_early(self):
        """验证客户端中途停止消费时仍然结束追踪 span。"""
        span = RecordingSpan()

        async def run():
            """消费首个事件后主动关闭 Chat 服务流。"""
            service = ChatStreamService(FakeGraph(), "token")
            iterator = service.stream({"request_id": "r1", "conversation_id": "c1"})
            await iterator.__anext__()
            await iterator.aclose()

        with patch("familyos_agent.transport.grpc.chat.trace_run", return_value=span):
            asyncio.run(run())

        self.assertEqual(span.end_count, 1)

    def test_ends_trace_when_graph_fails(self):
        """验证 Graph 异常退出时仍然结束追踪 span。"""
        span = RecordingSpan()

        async def run():
            """消费会在处理中抛错的 Chat 服务流。"""
            service = ChatStreamService(FailingGraph(), "token")
            return [event async for event in service.stream({"request_id": "r1", "conversation_id": "c1"})]

        with patch("familyos_agent.transport.grpc.chat.trace_run", return_value=span):
            with self.assertRaises(RuntimeError):
                asyncio.run(run())

        self.assertEqual(span.end_count, 1)


if __name__ == "__main__":
    unittest.main()
