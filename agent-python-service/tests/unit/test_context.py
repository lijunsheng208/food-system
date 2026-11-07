"""验证多轮会话的滚动摘要和上下文预算行为。"""

import asyncio
import unittest

from familyos_agent.agent.context import prepare_conversation_context


class SummaryModel:
    """记录摘要请求并返回可控的压缩结果。"""

    def __init__(self, response="新摘要"):
        """初始化模型返回值和请求记录。"""
        self.response = response
        self.prompts = []

    async def ainvoke(self, messages):
        """记录压缩提示词并返回模拟摘要。"""
        self.prompts.append(messages)
        if isinstance(self.response, Exception):
            raise self.response
        return type("Response", (), {"content": self.response})()


class ConversationContextTest(unittest.TestCase):
    """验证历史按滚动摘要覆盖游标压缩，同时保留最近原文。"""

    # 长历史应压缩超出近期窗口的轮次，并通过游标只标记成功摘要部分。
    def test_summarizes_older_messages_and_retains_recent_turns(self):
        history = []
        for index in range(7):
            history.extend([
                {"role": "user", "content": "用户轮次%d" % index, "created_at": index, "message_id": "u%d" % index},
                {"role": "assistant", "content": "助手轮次%d" % index, "created_at": index, "message_id": "a%d" % index},
            ])
        model = SummaryModel()

        messages, summary, cursor = asyncio.run(prepare_conversation_context(model, history, "已有摘要"))

        self.assertEqual(summary, "新摘要")
        self.assertEqual(len(messages), 12)
        self.assertEqual(messages[0]["content"], "用户轮次1")
        self.assertEqual(messages[-1]["content"], "助手轮次6")
        self.assertEqual(cursor, {"created_at": 0, "message_id": "a0"})
        self.assertIn("已有摘要", model.prompts[0][1]["content"])

    # 摘要模型失败时不推进持久化游标，调用方可在下一轮重试压缩。
    def test_summary_failure_keeps_previous_summary_and_does_not_advance_cursor(self):
        history = []
        for index in range(7):
            history.extend([
                {"role": "user", "content": "用户轮次%d" % index, "message_id": "u%d" % index},
                {"role": "assistant", "content": "助手轮次%d" % index, "message_id": "a%d" % index},
            ])

        messages, summary, cursor = asyncio.run(prepare_conversation_context(SummaryModel(RuntimeError("failed")), history, "旧摘要"))

        self.assertEqual(summary, "旧摘要")
        self.assertIsNone(cursor)
        self.assertEqual(len(messages), 14)
        self.assertEqual(messages[0]["content"], "用户轮次0")

    # 尚未超过近期窗口时不触发额外模型请求，也不改变原文顺序。
    def test_short_history_does_not_call_summary_model(self):
        model = SummaryModel()
        source = [{"role": "user", "content": "问题"}, {"role": "assistant", "content": "回答"}]

        messages, summary, cursor = asyncio.run(prepare_conversation_context(model, source, "长期摘要"))

        self.assertEqual(messages, source)
        self.assertEqual(summary, "长期摘要")
        self.assertIsNone(cursor)
        self.assertEqual(model.prompts, [])


if __name__ == "__main__":
    unittest.main()
