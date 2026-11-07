"""会话历史压缩与上下文预算控制。"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

_RECENT_TURNS = 6
_MAX_CONTEXT_TOKENS = 6000
_MAX_SUMMARY_TOKENS = 1600


def _content(message: Mapping[str, Any]) -> str:
    """兼容纯文本和多模态消息内容，供预算估算与摘要使用。"""
    value = message.get("content", "")
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) if isinstance(item, Mapping) else str(item) for item in value)
    return str(value or "")


def _estimate_tokens(messages: Sequence[Mapping[str, Any]]) -> int:
    """按中英文混合文本估算 Token 数，给缺少 tokenizer 的兼容模型提供保守预算。"""
    return sum(max(1, (len(_content(message)) + 2) // 3) for message in messages)


async def prepare_conversation_context(
    model: Any,
    messages: Sequence[Mapping[str, Any]],
    existing_summary: str = "",
) -> tuple[list[dict[str, str]], str, dict[str, Any] | None]:
    """将较早对话滚动压缩为摘要，并返回预算内的摘要加近期原文。"""
    history = [dict(message) for message in messages if message.get("role") in ("user", "assistant")]
    recent_start = max(0, len(history) - _RECENT_TURNS * 2)
    older, recent = history[:recent_start], history[recent_start:]
    summary = existing_summary.strip()
    compression_succeeded = not older

    cursor = None
    if older:
        prompt = [
            {"role": "system", "content": (
                "你负责压缩 FamilyOS 对话记忆。合并旧摘要与新增对话，保留用户明确陈述且未来有用的事实、"
                "饮食偏好/忌口/过敏、约束、未解决事项及重要更正；区分用户事实与助手建议，不推断、不补充。"
                "输出简洁中文要点，最多 1600 token。"
            )},
            {"role": "user", "content": "旧摘要：\n%s\n\n新增较早对话：\n%s" % (
                summary or "（无）",
                "\n".join("%s：%s" % (item.get("role"), _content(item)) for item in older),
            )},
        ]
        try:
            response = await model.ainvoke(prompt)
            candidate = getattr(response, "content", "")
            if isinstance(candidate, list):
                candidate = _content({"content": candidate})
            candidate = str(candidate or "").strip()
            if not candidate:
                raise ValueError("上下文摘要为空")
            summary = candidate[: _MAX_SUMMARY_TOKENS * 3]
            last_summarized = older[-1]
            cursor = {"created_at": last_summarized.get("created_at"), "message_id": last_summarized.get("message_id")}
            compression_succeeded = True
        except Exception:
            # 摘要模型故障不应中断主问答；沿用上次摘要并尽量保留更多原始历史。
            logger.exception("会话上下文压缩失败，沿用已有摘要")

    if not compression_succeeded:
        # 压缩失败时尽量保留更多原始历史，避免固定近期窗口造成上下文突失。
        recent = history
    while recent and _estimate_tokens(recent) > _MAX_CONTEXT_TOKENS:
        recent = recent[2:] if len(recent) > 2 else recent[1:]
    recent = [{"role": str(item["role"]), "content": _content(item)} for item in recent]
    return recent, summary, cursor
