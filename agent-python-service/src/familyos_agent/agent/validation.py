"""D4 回答、引用和饮食约束校验。"""

import re
from typing import Any, Mapping, Sequence


def validate_answer(answer: str, documents: Sequence[Any] = (), citations: Sequence[Mapping[str, Any]] = (), constraints: Mapping[str, Any] = ()) -> tuple[bool, str]:
    """校验回答非空、无敏感凭证且引用和已知饮食约束不冲突。"""
    text = str(answer or "").strip()
    if not text:
        return False, "ANSWER_EMPTY"
    if re.search(r"(?:sk-[A-Za-z0-9]|Bearer\s+[A-Za-z0-9._-]{16,}|password\s*[:=])", text, re.I):
        return False, "SENSITIVE_OUTPUT"
    known_ids = {str(item.get("chunk_id")) for item in documents if isinstance(item, Mapping) and item.get("chunk_id")}
    for citation in citations:
        if known_ids and str(citation.get("chunk_id", "")) not in known_ids:
            return False, "CITATION_NOT_FOUND"
    blocked = constraints.get("allergens", constraints.get("忌口", [])) if isinstance(constraints, Mapping) else []
    if isinstance(blocked, str):
        blocked = [blocked]
    for ingredient in blocked or []:
        if str(ingredient).strip() and str(ingredient).lower() in text.lower():
            return False, "DIETARY_CONSTRAINT_VIOLATION"
    return True, ""
