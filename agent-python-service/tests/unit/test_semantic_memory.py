import asyncio
import unittest

from familyos_agent.agent.semantic_memory import extract_semantic_memories, format_semantic_memories


class FixedSemanticModel:
    """返回固定语义记忆提取结果。"""

    def __init__(self, content):
        """保存模型响应内容。"""
        self.content = content

    async def ainvoke(self, messages):
        """模拟现有 OpenAI-compatible 模型异步调用。"""
        return type("Response", (), {"content": self.content})()


class SemanticMemoryExtractionTest(unittest.TestCase):
    """验证开放式经历只在满足安全边界时进入语义记忆。"""

    def test_extracts_reusable_experience_and_feedback(self):
        """明确的历史经历和操作反馈应被保留。"""
        model = FixedSemanticModel(
            '[{"memory_type":"experience","content":"用户上次制作红烧肉时炒糖色失败。","importance":0.9},'
            '{"memory_type":"feedback","content":"用户希望复杂火候步骤提供更细说明。","importance":0.8}]'
        )

        result = asyncio.run(extract_semantic_memories(model, "上次炒糖色失败，以后火候讲细一点"))

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["memory_type"], "experience")

    def test_filters_unknown_low_importance_and_oversized_memories(self):
        """未知类别、低重要度和过长内容不得进入向量库。"""
        model = FixedSemanticModel("[" + ",".join([
            '{"memory_type":"secret","content":"内容","importance":0.9}',
            '{"memory_type":"habit","content":"偶尔尝试一次","importance":0.2}',
            '{"memory_type":"feedback","content":"%s","importance":0.9}' % ("长" * 501),
        ]) + "]")

        result = asyncio.run(extract_semantic_memories(model, "测试"))

        self.assertEqual(result, [])

    def test_formats_only_allowed_recalled_memories(self):
        """召回上下文只格式化允许类别并受数量约束。"""
        result = format_semantic_memories([
            {"memory_type": "habit", "content": "用户习惯周日集中备餐"},
            {"memory_type": "unknown", "content": "不应出现"},
        ])

        self.assertEqual(result, "- habit：用户习惯周日集中备餐")


if __name__ == "__main__":
    unittest.main()
