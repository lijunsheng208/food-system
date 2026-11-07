"""用户长期结构化事实的提取、校验与上下文格式化。"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


# 核心 Key 供业务稳定更新，扩展 Key 只承接同类别中未被核心字段覆盖的长期事实。
MEMORY_SCHEMA: dict[str, dict[str, Any]] = {
    "family_size": {"category": "household", "type": "integer", "minimum": 1, "maximum": 50},
    "has_children": {"category": "household", "type": "boolean"},
    "has_elderly": {"category": "household", "type": "boolean"},
    "household_other": {"category": "household", "type": "fact_list"},
    "available_appliances": {"category": "equipment", "type": "string_list"},
    "primary_cooking_device": {"category": "equipment", "type": "string"},
    "equipment_other": {"category": "equipment", "type": "fact_list"},
    "cooking_level": {"category": "skill", "type": "enum", "values": ["beginner", "intermediate", "advanced"]},
    "skill_other": {"category": "skill", "type": "fact_list"},
    "weekday_cooking_minutes": {"category": "schedule", "type": "integer", "minimum": 1, "maximum": 1440},
    "usual_cooking_period": {"category": "schedule", "type": "enum", "values": ["morning", "noon", "evening", "flexible"]},
    "meal_prep_habit": {"category": "schedule", "type": "fact"},
    "schedule_other": {"category": "schedule", "type": "fact_list"},
    "cooking_goal": {"category": "goal", "type": "string"},
    "goal_other": {"category": "goal", "type": "fact_list"},
    "preferred_language": {"category": "locale", "type": "string"},
    "region": {"category": "locale", "type": "string"},
    "locale_other": {"category": "locale", "type": "fact_list"},
}

_SYSTEM_PROMPT = """你负责从用户本轮消息中提取可长期复用的结构化事实。
只提取用户明确陈述、相对稳定且不属于饮食偏好的事实；不要从助手回答推断，不要猜测。
只能选择下面列出的 key，禁止创造新 key；核心字段无法表达但未来确实有用时，选择相应的 *_other 或 *_habit：
- household：family_size(integer)、has_children(boolean)、has_elderly(boolean)、household_other(fact_list)
- equipment：available_appliances(string_list)、primary_cooking_device(string)、equipment_other(fact_list)
- skill：cooking_level(enum: beginner/intermediate/advanced)、skill_other(fact_list)
- schedule：weekday_cooking_minutes(integer)、usual_cooking_period(enum: morning/noon/evening/flexible)、meal_prep_habit(fact)、schedule_other(fact_list)
- goal：cooking_goal(string)、goal_other(fact_list)
- locale：preferred_language(string)、region(string)、locale_other(fact_list)
fact 的 value 必须是 {"name":"简短事实名","description":"用户明确表达的事实"}；
fact_list 的 value 是上述 fact 对象的数组，最多 20 项。
integer、boolean、string、string_list 和 enum 必须使用对应的 JSON 类型，不要把数字或布尔值写成字符串。
如果当前消息为已有 string_list 或 fact_list 增加内容，应结合提供的当前记忆输出合并后的完整列表；
如果用户明确更正或删除旧内容，则以当前消息为准。不要仅因为当前记忆存在就重复输出未涉及的 Key。
不要提取饮食偏好、忌口或过敏，它们由独立业务服务管理；也不要提取密码、令牌、联系方式、
精确住址、医疗诊断、金融信息或一次性临时要求。
输出 JSON 数组，每项为 {"category":"...","key":"...","value":任意合法JSON值,"confidence":0到1}。
没有符合项时输出 []。"""


def _response_content(response: Any) -> str:
    """读取 OpenAI-compatible 模型响应中的纯文本内容。"""
    value = getattr(response, "content", response)
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) if isinstance(item, Mapping) else str(item) for item in value)
    return str(value or "")


def _normalize_memory_value(definition: Mapping[str, Any], value: Any) -> Any | None:
    """根据标准 Key 的 Value Schema 校验并规范化模型输出，类型不符时拒绝写入。"""
    value_type = definition["type"]
    if value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        if value < int(definition["minimum"]) or value > int(definition["maximum"]):
            return None
        return value
    if value_type == "boolean":
        return value if isinstance(value, bool) else None
    if value_type == "string":
        normalized = value.strip() if isinstance(value, str) else ""
        return normalized if 0 < len(normalized) <= 500 else None
    if value_type == "enum":
        return value if isinstance(value, str) and value in definition["values"] else None
    if value_type == "string_list":
        if not isinstance(value, list) or not 0 < len(value) <= 20:
            return None
        normalized_items = []
        for item in value:
            normalized = item.strip() if isinstance(item, str) else ""
            if not normalized or len(normalized) > 100:
                return None
            if normalized not in normalized_items:
                normalized_items.append(normalized)
        return normalized_items
    if value_type == "fact":
        if not isinstance(value, Mapping):
            return None
        name, description = value.get("name", ""), value.get("description", "")
        if not isinstance(name, str) or not isinstance(description, str):
            return None
        name, description = name.strip(), description.strip()
        if not name or not description or len(name) > 100 or len(description) > 500:
            return None
        return {"name": name, "description": description}
    if value_type == "fact_list":
        if not isinstance(value, list) or not 0 < len(value) <= 20:
            return None
        normalized_facts = []
        for item in value:
            normalized = _normalize_memory_value({"type": "fact"}, item)
            if normalized is None:
                return None
            if normalized not in normalized_facts:
                normalized_facts.append(normalized)
        return normalized_facts
    return None


async def extract_long_term_memories(
    model: Any,
    user_message: str,
    existing_memories: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """让现有模型将用户原话映射到固定 Schema，并返回通过程序校验的候选事实。"""
    if model is None or not user_message.strip():
        return []
    existing_context = format_long_term_memories(existing_memories)
    user_content = user_message[:4000]
    if existing_context:
        user_content = "当前有效长期记忆：\n%s\n\n本轮用户原话：\n%s" % (existing_context, user_content)
    response = await model.ainvoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ])
    content = _response_content(response).strip()
    if content.startswith("```"):
        content = content.strip("`").removeprefix("json").strip()
    parsed = json.loads(content)
    if not isinstance(parsed, list):
        return []
    result_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in parsed:
        if not isinstance(item, Mapping):
            continue
        category, key = str(item.get("category", "")).strip(), str(item.get("key", "")).strip()
        definition = MEMORY_SCHEMA.get(key)
        if definition is None or category != definition["category"]:
            continue
        value = _normalize_memory_value(definition, item.get("value"))
        if value is None:
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.8))))
        except (TypeError, ValueError):
            confidence = 0.8
        if confidence < 0.7:
            continue
        candidate = {
            "category": category,
            "key": key,
            "value": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            "confidence": confidence,
        }
        identity = (category, key)
        if identity not in result_by_key or confidence > result_by_key[identity]["confidence"]:
            result_by_key[identity] = candidate
    return list(result_by_key.values())[:20]


def _display_memory_value(raw_value: Any) -> str:
    """将数据库中的 JSON Value 转成可读文本，并兼容升级前保存的普通字符串。"""
    value = raw_value
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return ""
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return text
    elif raw_value is None:
        return ""
    if isinstance(value, Mapping) and value.get("name") and value.get("description"):
        return "%s（%s）" % (value["name"], value["description"])
    if isinstance(value, list):
        values = []
        for item in value:
            if isinstance(item, Mapping) and item.get("name") and item.get("description"):
                values.append("%s（%s）" % (item["name"], item["description"]))
            else:
                values.append(str(item))
        return "、".join(values)
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def format_long_term_memories(memories: Sequence[Mapping[str, Any]]) -> str:
    """将长期事实格式化到字符预算内，避免持久化内容无限扩大模型上下文。"""
    lines = []
    total_chars = 0
    for item in memories[:50]:
        category = str(item.get("category", "")).strip()
        key = str(item.get("memory_key", item.get("key", ""))).strip()
        value = _display_memory_value(item.get("memory_value", item.get("value", "")))
        definition = MEMORY_SCHEMA.get(key)
        # 升级前自由生成的旧 Key 不再注入模型，避免历史 Key 漂移继续影响回答。
        if definition is not None and category == definition["category"] and value:
            line = "- %s/%s：%s" % (category[:64], key[:128], value[:1000])
            if total_chars + len(line) > 8000:
                break
            lines.append(line)
            total_chars += len(line) + 1
    return "\n".join(lines)
