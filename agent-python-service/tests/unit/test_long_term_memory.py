import asyncio
import unittest

from familyos_agent.agent.long_term_memory import extract_long_term_memories, format_long_term_memories


class FixedResponseModel:
    """返回固定 OpenAI-compatible 响应，隔离长期记忆解析测试。"""

    def __init__(self, content):
        """保存测试响应正文并记录模型调用次数。"""
        self.content = content
        self.calls = 0
        self.last_messages = []

    async def ainvoke(self, messages):
        """模拟现有模型的异步调用接口。"""
        self.calls += 1
        self.last_messages = messages
        return type("Response", (), {"content": self.content})()


class LongTermMemoryTest(unittest.TestCase):
    """验证长期结构化记忆的模型输出校验和上下文格式化。"""

    def test_extracts_allowed_stable_memories(self):
        """允许类别和足够置信度的事实应被规范化保留。"""
        model = FixedResponseModel('[{"category":"household","key":"family_size","value":4,"confidence":0.95}]')

        result = asyncio.run(extract_long_term_memories(model, "我们家一共四个人"))

        self.assertEqual(result, [{"category": "household", "key": "family_size", "value": "4", "confidence": 0.95}])
        self.assertEqual(model.calls, 1)

    def test_accepts_markdown_json_and_filters_unsafe_categories(self):
        """兼容 fenced JSON，并丢弃饮食偏好、敏感类别和低置信度结果。"""
        model = FixedResponseModel(
            "```json\n["
            '{"category":"equipment","key":"available_appliances","value":["oven","oven"],"confidence":0.8},'
            '{"category":"dietary","key":"allergy","value":"花生","confidence":0.99},'
            '{"category":"locale","key":"preferred_language","value":"中文","confidence":0.5}'
            "]\n```"
        )

        result = asyncio.run(extract_long_term_memories(model, "我有烤箱"))

        self.assertEqual(result, [{"category": "equipment", "key": "available_appliances", "value": '["oven"]', "confidence": 0.8}])

    def test_rejects_unknown_key_category_mismatch_and_invalid_value_type(self):
        """模型新造 Key、跨类别选 Key 或输出错误类型时都不得形成长期记忆。"""
        model = FixedResponseModel(
            "["
            '{"category":"household","key":"number_of_people","value":4,"confidence":0.9},'
            '{"category":"goal","key":"family_size","value":4,"confidence":0.9},'
            '{"category":"household","key":"family_size","value":"四人","confidence":0.9}'
            "]"
        )

        result = asyncio.run(extract_long_term_memories(model, "我们家四个人"))

        self.assertEqual(result, [])

    def test_accepts_extension_fact_without_allowing_dynamic_key(self):
        """白名单外稳定信息可进入类别扩展容器，但扩展内容仍须符合 Fact Schema。"""
        model = FixedResponseModel(
            '[{"category":"schedule","key":"meal_prep_habit",'
            '"value":{"name":"周末集中备餐","description":"周日提前准备三天餐食"},"confidence":0.9}]'
        )

        result = asyncio.run(extract_long_term_memories(model, "我每周日会提前准备三天的饭"))

        self.assertEqual(result, [{
            "category": "schedule",
            "key": "meal_prep_habit",
            "value": '{"name":"周末集中备餐","description":"周日提前准备三天餐食"}',
            "confidence": 0.9,
        }])

    def test_accepts_multiple_facts_in_limited_extension_container(self):
        """通用扩展 Key 可保存多个规范事实，避免被单条扩展信息限制死。"""
        model = FixedResponseModel(
            '[{"category":"equipment","key":"equipment_other","value":['
            '{"name":"容量限制","description":"烤箱容量为二十升"},'
            '{"name":"火力特点","description":"燃气灶左侧火力较弱"}],"confidence":0.88}]'
        )

        result = asyncio.run(extract_long_term_memories(model, "我家的烤箱只有二十升，而且燃气灶左边火比较小"))

        self.assertEqual(result[0]["key"], "equipment_other")
        self.assertIn("容量限制", result[0]["value"])
        self.assertIn("火力特点", result[0]["value"])

    def test_keeps_highest_confidence_for_duplicate_key(self):
        """同一轮模型重复输出相同 Key 时只保留置信度最高的候选事实。"""
        model = FixedResponseModel(
            '[{"category":"household","key":"family_size","value":3,"confidence":0.8},'
            '{"category":"household","key":"family_size","value":4,"confidence":0.95}]'
        )

        result = asyncio.run(extract_long_term_memories(model, "我们家四个人"))

        self.assertEqual(result[0]["value"], "4")
        self.assertEqual(result[0]["confidence"], 0.95)

    def test_provides_existing_collection_for_merge_or_correction(self):
        """列表类记忆提取应获得旧值，以便模型生成合并、删除或更正后的完整集合。"""
        model = FixedResponseModel(
            '[{"category":"equipment","key":"available_appliances",'
            '"value":["air_fryer","oven"],"confidence":0.9}]'
        )

        result = asyncio.run(extract_long_term_memories(model, "我还有烤箱", [{
            "category": "equipment",
            "memory_key": "available_appliances",
            "memory_value": '["air_fryer"]',
        }]))

        self.assertIn("air_fryer", model.last_messages[1]["content"])
        self.assertEqual(result[0]["value"], '["air_fryer","oven"]')

    def test_empty_message_does_not_call_model(self):
        """空消息没有可提取事实，不应消耗模型调用。"""
        model = FixedResponseModel("[]")

        result = asyncio.run(extract_long_term_memories(model, "   "))

        self.assertEqual(result, [])
        self.assertEqual(model.calls, 0)

    def test_invalid_json_is_reported_to_caller(self):
        """无效模型输出应抛错，由会话层记录降级原因。"""
        with self.assertRaises(ValueError):
            asyncio.run(extract_long_term_memories(FixedResponseModel("not-json"), "我常用烤箱"))

    def test_formats_database_and_extraction_shapes(self):
        """数据库字段和模型提取字段都能转换为简洁上下文。"""
        result = format_long_term_memories([
            {"category": "household", "memory_key": "family_size", "memory_value": "4"},
            {"category": "skill", "key": "cooking_level", "value": '"beginner"'},
            {"category": "equipment", "key": "available_appliances", "value": ["air_fryer", "oven"]},
            {"category": "equipment", "key": "llm_created_key", "value": "旧自由 Key"},
        ])

        self.assertEqual(result, "- household/family_size：4\n- skill/cooking_level：beginner\n- equipment/available_appliances：air_fryer、oven")


if __name__ == "__main__":
    unittest.main()
