"""开放式用户经历的语义记忆提取与上下文格式化。"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence


_ALLOWED_TYPES = {"experience", "feedback", "habit", "history_issue"}
_SYSTEM_PROMPT = """你负责从用户本轮原话中提取未来相似任务可能有帮助的开放式长期记忆。
只提取用户明确表达的个人经历、实际操作反馈、长期行为习惯或曾遇到的问题；不要提取助手的建议，
不要猜测，也不要保存一次性请求。家庭人数、设备清单、技能水平、地区等固定事实由结构化记忆管理；
口味、菜系、忌口和过敏由饮食偏好服务管理，这里不要重复提取。
禁止保存密码、令牌、联系方式、精确住址、医疗诊断、金融信息及第三方隐私。
memory_type 只能是 experience、feedback、habit、history_issue。
content 必须是脱离当前对话仍可理解的简洁中文事实，最多 500 字；importance 为 0 到 1。
输出 JSON 数组，每项格式为 {"memory_type":"...","content":"...","importance":0到1}；没有则输出 []。"""


def _response_content(response: Any) -> str:
    """读取 OpenAI-compatible 模型响应中的文本。"""
    value = getattr(response, "content", response)
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) if isinstance(item, Mapping) else str(item) for item in value)
    return str(value or "")


async def extract_semantic_memories(model: Any, user_message: str) -> list[dict[str, Any]]:
    """从用户原话提取开放式长期记忆候选，并执行类别、长度和重要度校验。"""
    if model is None or not user_message.strip():
        return []
    response = await model.ainvoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message[:4000]},
    ])
    content = _response_content(response).strip()
    if content.startswith("```"):
        content = content.strip("`").removeprefix("json").strip()
    parsed = json.loads(content)
    if not isinstance(parsed, list):
        return []
    candidates = []
    seen = set()
    for item in parsed:
        if not isinstance(item, Mapping):
            continue
        memory_type = str(item.get("memory_type", "")).strip()
        memory_content = str(item.get("content", "")).strip()
        if memory_type not in _ALLOWED_TYPES or not memory_content or len(memory_content) > 500:
            continue
        try:
            importance = max(0.0, min(1.0, float(item.get("importance", 0.7))))
        except (TypeError, ValueError):
            importance = 0.7
        if importance < 0.6:
            continue
        identity = (memory_type, memory_content)
        if identity not in seen:
            seen.add(identity)
            candidates.append({"memory_type": memory_type, "content": memory_content, "importance": importance})
    return candidates[:10]


def format_semantic_memories(memories: Sequence[Mapping[str, Any]]) -> str:
    """按相关度和数量边界格式化语义记忆，避免开放式历史无限占用上下文。"""
    lines = []
    total_chars = 0
    for item in memories[:10]:
        memory_type = str(item.get("memory_type", "")).strip()
        content = str(item.get("content", "")).strip()
        if memory_type not in _ALLOWED_TYPES or not content:
            continue
        line = "- %s：%s" % (memory_type, content[:500])
        if total_chars + len(line) > 4000:
            break
        lines.append(line)
        total_chars += len(line) + 1
    return "\n".join(lines)
