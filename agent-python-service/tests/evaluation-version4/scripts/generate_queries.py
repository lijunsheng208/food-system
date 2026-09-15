"""从已索引的菜谱 Chunk 映射生成 V4 分层检索评测数据。"""

import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


QUOTAS = {
    "dish_lookup": 30,
    "ingredient_fact": 45,
    "calculation_fact": 45,
    "procedure_fact": 45,
    "cross_parent": 60,
    "recommendation": 45,
    "constraint": 20,
    "unanswerable": 10,
}

CATEGORY_LABELS = {
    "aquatic": "水产菜",
    "breakfast": "早餐",
    "condiment": "调味品",
    "dessert": "甜点",
    "drink": "饮品",
    "meat_dish": "家常肉菜",
    "semi-finished": "半成品快手菜",
    "soup": "汤品",
    "staple": "主食",
    "vegetable_dish": "蔬菜菜肴",
}

SECTION_LABELS = {
    "必备原料和工具": "ingredients",
    "计算": "calculation",
    "操作": "operation",
    "附加内容": "additional",
}

GENERIC_INGREDIENTS = {
    "水",
    "清水",
    "开水",
    "油",
    "食用油",
    "植物油",
    "盐",
    "食盐",
    "食用盐",
    "糖",
    "白糖",
    "白砂糖",
    "生抽",
    "酱油",
    "料酒",
    "鸡精",
    "味精",
    "淀粉",
    "生粉",
}

TOOL_MARKERS = (
    "锅",
    "碗",
    "盘",
    "碟",
    "杯",
    "盆",
    "刀",
    "砧板",
    "烤箱",
    "空气炸锅",
    "微波炉",
    "电饭煲",
    "打蛋器",
    "搅拌机",
    "料理机",
    "漏勺",
    "蒸笼",
    "模具",
    "容器",
    "冰箱",
    "保鲜膜",
    "筷子",
    "剪刀",
)

COOKING_ACTIONS = (
    "焯水",
    "翻炒",
    "煎",
    "炒",
    "蒸",
    "炖",
    "煮",
    "烤",
    "炸",
    "腌制",
    "腌",
    "搅拌",
    "切",
    "焖",
    "收汁",
    "冷藏",
    "加热",
)

FORBIDDEN_QUERY_PHRASES = ("根据文档", "请检索", "根据资料", "根据菜谱库")


# _normalize_text 统一去除空白和标点，用于证据文本匹配。
def _normalize_text(value: str) -> str:
    return re.sub(r"[\s\u3000，。、“”‘’：:；;、（）()【】\[\]!?！？\-—_/`*#]", "", value.lower())


# _stable_digest 为选择顺序和 ID 提供跨运行稳定的摘要。
def _stable_digest(*values: object) -> str:
    payload = "\n".join(str(value) for value in values)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


# _stable_id 生成便于阅读且确定性的评测记录 ID。
def _stable_id(prefix: str, *values: object) -> str:
    return f"{prefix}-{_stable_digest(*values)[:12]}"


# _clean_markdown 清除会干扰原料和操作短语抽取的 Markdown 标记。
def _clean_markdown(value: str) -> str:
    value = re.sub(r"!\[[^]]*]\([^)]*\)", "", value)
    value = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", value)
    value = re.sub(r"^[\s>*+-]+", "", value)
    value = re.sub(r"^\d+[.)、]\s*", "", value)
    value = value.replace("`", "").replace("**", "").replace("__", "")
    return re.sub(r"\s+", " ", value).strip(" 。；;，,")


# _bullet_lines 提取一个 Child 中可作为事实标签的列表项。
def _bullet_lines(content: str) -> List[str]:
    values = []
    for line in content.splitlines():
        if re.match(r"^\s*(?:[-*+]\s+|\d+[.)、]\s*)", line):
            cleaned = _clean_markdown(line)
            if cleaned:
                values.append(cleaned)
    return values


# _clean_ingredient 从原料或计算列表项中提取可用于自然 Query 的原料名。
def _clean_ingredient(value: str) -> str:
    cleaned = _clean_markdown(value)
    cleaned = re.sub(r"^(?:必备|可选|推荐|调料|原料|食材)[:：]?", "", cleaned)
    cleaned = re.split(r"[（(=:：]", cleaned, maxsplit=1)[0]
    cleaned = re.split(r"\d|约|适量|少许|若干", cleaned, maxsplit=1)[0]
    cleaned = re.split(r"[，,；;、]", cleaned, maxsplit=1)[0]
    cleaned = cleaned.strip()
    cleaned = re.sub(r"(?:的)?用量(?:为)?$", "", cleaned)
    cleaned = re.sub(r"[一二三四五六七八九十两半]+(?:个|只|份|包|盒|根|颗|片|瓣|勺|杯)$", "", cleaned)
    cleaned = re.sub(r"^[一二三四五六七八九十两半]+(?:个|只|份|包|盒|根|颗|片|瓣|勺|杯)", "", cleaned)
    cleaned = re.sub(r"\s+[A-Za-z]$", "", cleaned)
    cleaned = re.sub(r"^[^A-Za-z0-9\u4e00-\u9fff]+", "", cleaned)
    return cleaned.strip(" -。；;，,")


# _valid_ingredient 判断抽取值是否适合作为推荐或事实 Query 的语义锚点。
def _valid_ingredient(value: str) -> bool:
    return (
        1 <= len(value) <= 10
        and bool(re.search(r"[\u4e00-\u9fff]", value))
        and value not in GENERIC_INGREDIENTS
        and not any(marker in value for marker in TOOL_MARKERS)
        and (len(value) > 1 or value in {"葱", "姜", "蒜", "蛋", "虾", "蟹", "鱼", "盐", "糖", "醋", "油"})
        and not any(
            word in value
            for word in (
                "万物",
                "步骤",
                "做法",
                "操作",
                "自行",
                "根据",
                "见附加",
                "版本",
                "准备",
                "用量",
                "原料",
                "工具",
                "直径",
                "可制作",
            )
        )
    )


# _section_from_content 仅识别 Child 开头的二级标题，避免把首页目录误当作章节。
def _section_from_content(content: str) -> str | None:
    match = re.match(r"^##\s+([^\n]+)", content.strip())
    if not match:
        return None
    return SECTION_LABELS.get(match.group(1).strip())


# _extract_title 从首页一级标题提取规范菜名。
def _extract_title(source: str, chunks: Sequence[Mapping[str, Any]]) -> str:
    for chunk in chunks:
        match = re.search(r"(?m)^#\s+(.+?)\s*$", str(chunk["content"]))
        if match:
            return re.sub(r"的做法$", "", match.group(1).strip()).strip()
    return Path(source).stem


# _extract_duration_minutes 从菜谱简介优先抽取总制作时长。
def _extract_duration_minutes(content: str) -> float | None:
    patterns = (
        r"(?:全程|总时长|制作时长|从.+?到.+?|一般|大约|约|预计|只需|需要)[^。\n]{0,24}?(\d+(?:\.\d+)?)\s*(分钟|分|小时)",
        r"(\d+(?:\.\d+)?)\s*(?:至|到|[-~～])\s*(\d+(?:\.\d+)?)\s*(分钟|分|小时)",
    )
    range_match = re.search(patterns[1], content)
    if range_match:
        value = float(range_match.group(2))
        return value * 60 if range_match.group(3) == "小时" else value
    match = re.search(patterns[0], content)
    if not match:
        return None
    value = float(match.group(1))
    return value * 60 if match.group(2) == "小时" else value


# _action_lines 将操作 Child 拆成可审计的单步事实文本。
def _action_lines(content: str) -> List[str]:
    values = _bullet_lines(content)
    if values:
        return values
    for line in content.splitlines():
        cleaned = _clean_markdown(line)
        if cleaned and not cleaned.startswith("#") and 8 <= len(cleaned) <= 180:
            values.append(cleaned)
    return values


# _matching_chunks 返回包含同一 Gold 事实的所有重叠 Child。
def _matching_chunks(chunks: Sequence[Mapping[str, Any]], fact: str) -> List[Mapping[str, Any]]:
    needle = _normalize_text(fact)
    if not needle:
        return []
    return [chunk for chunk in chunks if needle in _normalize_text(str(chunk["content"]))]


# _calculation_facts 从计算章节构造带原料锚点的具体用量事实。
def _calculation_facts(profile: Mapping[str, Any]) -> List[Dict[str, Any]]:
    chunks = profile["sections"].get("calculation", [])
    values = []
    seen = set()
    for chunk in chunks:
        for line in _bullet_lines(str(chunk["content"])):
            ingredient = _clean_ingredient(line)
            if not _valid_ingredient(ingredient) or not re.search(r"\d|份数|适量|少许", line):
                continue
            key = (ingredient, _normalize_text(line))
            if key in seen:
                continue
            seen.add(key)
            matches = _matching_chunks(chunks, line) or [chunk]
            ingredient_rank = next(
                (index for index, value in enumerate(profile["ingredients"]) if value == ingredient),
                len(profile["ingredients"]),
            )
            values.append(
                {
                    "ingredient": ingredient,
                    "fact": line,
                    "chunks": matches,
                    "score": 5 / (ingredient_rank + 1) + min(len(line), 80) / 100,
                }
            )
    return sorted(values, key=lambda item: (-float(item["score"]), str(item["fact"])))


# _operation_facts 从操作章节选取有主原料和明确动作的单步事实。
def _operation_facts(profile: Mapping[str, Any]) -> List[Dict[str, Any]]:
    chunks = profile["sections"].get("operation", [])
    ingredients = [value for value in profile["ingredients"] if _valid_ingredient(value)]
    values = []
    seen = set()
    for chunk in chunks:
        for line in _action_lines(str(chunk["content"])):
            anchor = next((value for value in ingredients if _normalize_text(value) in _normalize_text(line)), None)
            action = next((value for value in COOKING_ACTIONS if value in line), None)
            if not anchor or not action or len(line) < 8:
                continue
            key = _normalize_text(line)
            if key in seen:
                continue
            seen.add(key)
            matches = _matching_chunks(chunks, line) or [chunk]
            score = (
                20 / (ingredients.index(anchor) + 1)
                + 4 * bool(re.search(r"\d+(?:\.\d+)?\s*(?:秒|分钟|分|小时)", line))
                + 3 * bool(re.search(r"\d+(?:\.\d+)?\s*(?:℃|°C|摄氏度|度)", line, re.I))
                + min(len(line), 100) / 100
            )
            values.append({"anchor": anchor, "action": action, "fact": line, "chunks": matches, "score": score})
    return sorted(values, key=lambda item: (-float(item["score"]), str(item["fact"])))


# _load_profiles 将扁平 Chunk JSONL 恢复为按文档和章节组织的评测视图。
def _load_profiles(mapping_path: Path) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for line in mapping_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            grouped[str(row["source"])].append(row)

    profiles = []
    for source, rows in sorted(grouped.items()):
        chunks = sorted(rows, key=lambda item: (int(item.get("chunk_index", 0)), str(item["chunk_id"])))
        document_ids = {int(chunk["document_id"]) for chunk in chunks}
        if len(document_ids) != 1:
            raise ValueError(f"同一来源出现多个 document_id: {source}")
        sections: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        current_section = "overview"
        for chunk in chunks:
            detected = _section_from_content(str(chunk["content"]))
            if detected:
                current_section = detected
            sections[current_section].append(chunk)
        ingredient_lines = [
            line
            for chunk in sections.get("ingredients", [])
            for line in _bullet_lines(str(chunk["content"]))
        ]
        ingredients = []
        for line in ingredient_lines:
            value = _clean_ingredient(line)
            if value and value not in ingredients:
                ingredients.append(value)
        overview = "\n".join(str(chunk["content"]) for chunk in sections.get("overview", []))
        profile: Dict[str, Any] = {
            "source": source,
            "category": source.split("/", 1)[0],
            "document_id": next(iter(document_ids)),
            "title": _extract_title(source, chunks),
            "chunks": chunks,
            "sections": dict(sections),
            "ingredients": ingredients,
            "duration_minutes": _extract_duration_minutes(overview),
            "text": "\n".join(str(chunk["content"]) for chunk in chunks),
        }
        profile["calculation_facts"] = _calculation_facts(profile)
        profile["operation_facts"] = _operation_facts(profile)
        profiles.append(profile)
    return profiles


# _balanced_select 跨菜谱类别轮询选样，避免肉菜数量压倒其他类别。
def _balanced_select(
    profiles: Sequence[Mapping[str, Any]],
    count: int,
    salt: str,
    predicate: Any,
) -> List[Mapping[str, Any]]:
    by_category: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for profile in profiles:
        if profile["category"] in CATEGORY_LABELS and predicate(profile):
            by_category[str(profile["category"])].append(profile)
    for category, values in by_category.items():
        values.sort(key=lambda profile: _stable_digest(salt, category, profile["source"]))
    categories = sorted(by_category)
    positions = {category: 0 for category in categories}
    selected: List[Mapping[str, Any]] = []
    while len(selected) < count:
        progressed = False
        for category in categories:
            position = positions[category]
            if position >= len(by_category[category]):
                continue
            selected.append(by_category[category][position])
            positions[category] += 1
            progressed = True
            if len(selected) == count:
                break
        if not progressed:
            raise ValueError(f"{salt} 可用菜谱不足：需要 {count}，实际 {len(selected)}")
    return selected


# _evidence_group 将事实 Chunk 转成 Parent/Child 两级 Gold 证据组。
def _evidence_group(
    profile: Mapping[str, Any],
    group_name: str,
    heading: str,
    chunks: Sequence[Mapping[str, Any]],
    expected_facts: Sequence[str],
) -> Dict[str, Any]:
    child_ids = list(dict.fromkeys(str(chunk["chunk_id"]) for chunk in chunks))
    parent_ids = list(dict.fromkeys(str(chunk["parent_id"]) for chunk in chunks))
    if not child_ids or not parent_ids:
        raise ValueError(f"证据组缺少 Parent 或 Child: {profile['source']} {group_name}")
    child_counts = Counter(str(chunk["parent_id"]) for chunk in profile["chunks"])
    return {
        "group_id": _stable_id("eg", profile["source"], group_name, "|".join(child_ids)),
        "name": group_name,
        "required": True,
        "source": profile["source"],
        "heading_path": [heading],
        "acceptable_parent_ids": parent_ids,
        "parent_child_counts": {parent_id: child_counts[parent_id] for parent_id in parent_ids},
        "acceptable_child_ids": child_ids,
        "expected_facts": list(expected_facts),
    }


# _document_label 生成支持分级 NDCG 的文档 Gold 标签。
def _document_label(profile: Mapping[str, Any], relevance: int) -> Dict[str, Any]:
    return {
        "document_id": int(profile["document_id"]),
        "source": profile["source"],
        "relevance": relevance,
    }


# _dataset_split 保证同一主来源的 Query 始终落在相同数据分区。
def _dataset_split(group_key: str) -> str:
    return "test" if int(_stable_digest("split", group_key)[:8], 16) % 5 == 0 else "dev"


# _base_record 创建所有 Query 类型共享的可审计字段。
def _base_record(
    query_type: str,
    query: str,
    intent_key: str,
    category: str,
    relevant_documents: Sequence[Mapping[str, Any]],
    evidence_groups: Sequence[Mapping[str, Any]],
    difficulty: str,
    answerable: bool = True,
    **extra: Any,
) -> Dict[str, Any]:
    intent_id = _stable_id("intent", query_type, intent_key)
    # 单菜谱问题按来源分区，避免同一菜谱的不同问法泄漏到开发集和测试集两边。
    split_group = str(extra.get("primary_source") or intent_id)
    required_groups = [group for group in evidence_groups if group.get("required", True)]
    retrieval_scope = (
        "cross_parent" if len(required_groups) > 1 else "single_parent" if required_groups else "document_only"
    )
    parent_child_counts = [
        int(count)
        for group in required_groups
        for count in (group.get("parent_child_counts") or {}).values()
    ]
    record = {
        "query_id": _stable_id("q", query_type, intent_key, query),
        "intent_id": intent_id,
        "query": query,
        "query_type": query_type,
        "query_tags": [query_type],
        "query_style": "colloquial" if any(value in query for value in ("啥", "咋", "得")) else "standard",
        "source_category": category,
        "difficulty": difficulty,
        "retrieval_scope": retrieval_scope,
        "parent_child_count_bucket": ">1" if any(count > 1 for count in parent_child_counts) else "1" if parent_child_counts else "not_applicable",
        "answerable": answerable,
        "dataset_split": _dataset_split(split_group),
        "dataset_split_group": split_group,
        "relevant_documents": list(relevant_documents),
        "evidence_groups": list(evidence_groups),
        "constraints": [],
        "label_status": "needs_review",
        "generation_method": "deterministic_from_indexed_chunks",
    }
    record.update(extra)
    return record


# _dish_lookup_records 生成只要求命中正确文档的指定菜名 Query。
def _dish_lookup_records(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    selected = _balanced_select(profiles, QUOTAS["dish_lookup"], "dish_lookup", lambda profile: True)
    templates = ("{title}怎么做？", "想做{title}，菜谱是啥？", "{title}家常做法咋做？")
    records = []
    for index, profile in enumerate(selected):
        query = templates[index % len(templates)].format(title=profile["title"])
        records.append(
            _base_record(
                "dish_lookup",
                query,
                str(profile["source"]),
                str(profile["category"]),
                [_document_label(profile, 3)],
                [],
                "easy",
                primary_source=profile["source"],
            )
        )
    return records


# _ingredient_fact_records 生成以原料 Parent 为唯一必要证据的 Query。
def _ingredient_fact_records(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    selected = _balanced_select(
        profiles,
        QUOTAS["ingredient_fact"],
        "ingredient_fact",
        lambda profile: bool(profile["sections"].get("ingredients")),
    )
    templates = ("做{title}要准备哪些材料？", "{title}都得用啥原料和工具？", "我想做{title}，得提前备点啥？")
    records = []
    for index, profile in enumerate(selected):
        chunks = profile["sections"]["ingredients"]
        facts = [line for chunk in chunks for line in _bullet_lines(str(chunk["content"]))]
        group = _evidence_group(profile, "ingredients", "必备原料和工具", chunks, facts)
        query = templates[index % len(templates)].format(title=profile["title"])
        records.append(
            _base_record(
                "ingredient_fact",
                query,
                str(profile["source"]),
                str(profile["category"]),
                [_document_label(profile, 3)],
                [group],
                "easy",
                primary_source=profile["source"],
            )
        )
    return records


# _calculation_question 根据用量事实生成自然的单 Parent Query。
def _calculation_question(title: str, fact: Mapping[str, Any], variant: int) -> str:
    ingredient = fact["ingredient"]
    templates = (
        "做{title}时，{ingredient}的用量怎么计算？",
        "{title}每份得准备多少{ingredient}？",
        "准备做{title}，{ingredient}放多少合适？",
    )
    return templates[variant % len(templates)].format(title=title, ingredient=ingredient)


# _calculation_fact_records 生成绑定计算 Parent/Child 的具体用量 Query。
def _calculation_fact_records(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    selected = _balanced_select(
        profiles,
        QUOTAS["calculation_fact"],
        "calculation_fact",
        lambda profile: bool(profile["calculation_facts"]),
    )
    records = []
    for index, profile in enumerate(selected):
        fact = profile["calculation_facts"][0]
        group = _evidence_group(profile, "amount", "计算", fact["chunks"], [str(fact["fact"])])
        query = _calculation_question(str(profile["title"]), fact, index)
        records.append(
            _base_record(
                "calculation_fact",
                query,
                f"{profile['source']}:{fact['ingredient']}",
                str(profile["category"]),
                [_document_label(profile, 3)],
                [group],
                "medium",
                primary_source=profile["source"],
            )
        )
    return records


# _procedure_question 根据步骤中的时间、温度或动作生成具体操作 Query。
def _procedure_question(title: str, fact: Mapping[str, Any], variant: int) -> str:
    anchor = fact["anchor"]
    text = str(fact["fact"])
    if re.search(r"\d+(?:\.\d+)?\s*(?:℃|°C|摄氏度|度)", text, re.I) and re.search(
        r"\d+(?:\.\d+)?\s*(?:秒|分钟|分|小时)", text
    ):
        return f"做{title}时，涉及{anchor}的步骤要用多少度、处理多久？"
    if re.search(r"\d+(?:\.\d+)?\s*(?:秒|分钟|分|小时)", text):
        return f"做{title}时，{anchor}这一步需要处理多久？"
    templates = (
        "做{title}时，{anchor}这一环节具体怎么操作？",
        "{title}里的{anchor}应该咋处理？",
        "准备{title}时，{anchor}这一步要注意啥？",
    )
    return templates[variant % len(templates)].format(title=title, anchor=anchor)


# _procedure_fact_records 生成以具体操作 Child 为 Gold 的步骤 Query。
def _procedure_fact_records(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    selected = _balanced_select(
        profiles,
        QUOTAS["procedure_fact"],
        "procedure_fact",
        lambda profile: bool(profile["operation_facts"]),
    )
    records = []
    for index, profile in enumerate(selected):
        fact = profile["operation_facts"][0]
        group = _evidence_group(profile, "procedure", "操作", fact["chunks"], [str(fact["fact"])])
        query = _procedure_question(str(profile["title"]), fact, index)
        records.append(
            _base_record(
                "procedure_fact",
                query,
                f"{profile['source']}:{_normalize_text(str(fact['fact']))[:24]}",
                str(profile["category"]),
                [_document_label(profile, 3)],
                [group],
                "medium",
                primary_source=profile["source"],
            )
        )
    return records


# _cross_parent_records 生成计算与操作两个章节都必须命中的 Query。
def _cross_parent_records(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    selected = _balanced_select(
        profiles,
        QUOTAS["cross_parent"],
        "cross_parent",
        lambda profile: bool(profile["calculation_facts"] and profile["operation_facts"]),
    )
    records = []
    for index, profile in enumerate(selected):
        amount = profile["calculation_facts"][0]
        procedure = profile["operation_facts"][0]
        amount_group = _evidence_group(profile, "amount", "计算", amount["chunks"], [str(amount["fact"])])
        procedure_group = _evidence_group(profile, "procedure", "操作", procedure["chunks"], [str(procedure["fact"])])
        templates = (
            "做{title}时，{amount}要准备多少，{anchor}这一步又该怎么处理？",
            "{title}里的{amount}得备多少，{anchor}又该咋处理？",
            "想做{title}，{amount}放多少合适，{anchor}这一步要注意啥？",
        )
        query = templates[index % len(templates)].format(
            title=profile["title"], amount=amount["ingredient"], anchor=procedure["anchor"]
        )
        records.append(
            _base_record(
                "cross_parent",
                query,
                f"{profile['source']}:{amount['ingredient']}:{procedure['anchor']}",
                str(profile["category"]),
                [_document_label(profile, 3)],
                [amount_group, procedure_group],
                "hard",
                primary_source=profile["source"],
            )
        )
    return records


# _ingredient_index 为推荐和约束 Query 建立类别内完整相关文档集合。
def _ingredient_index(profiles: Sequence[Mapping[str, Any]]) -> Dict[tuple[str, str], List[Mapping[str, Any]]]:
    index: Dict[tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for profile in profiles:
        category = str(profile["category"])
        if category not in CATEGORY_LABELS:
            continue
        for ingredient in dict.fromkeys(profile["ingredients"]):
            if _valid_ingredient(ingredient):
                index[(category, ingredient)].append(profile)
    return index


# _balanced_key_select 按类别选择推荐/约束组合，避免单一类别占满配额。
def _balanced_key_select(candidates: Sequence[Mapping[str, Any]], count: int, salt: str) -> List[Mapping[str, Any]]:
    by_category: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_category[str(candidate["category"])].append(candidate)
    for category, values in by_category.items():
        values.sort(key=lambda item: _stable_digest(salt, category, item["key"]))
    categories = sorted(by_category)
    positions = {category: 0 for category in categories}
    selected = []
    while len(selected) < count:
        progressed = False
        for category in categories:
            position = positions[category]
            if position >= len(by_category[category]):
                continue
            selected.append(by_category[category][position])
            positions[category] += 1
            progressed = True
            if len(selected) == count:
                break
        if not progressed:
            raise ValueError(f"{salt} 候选不足：需要 {count}，实际 {len(selected)}")
    return selected


# _recommendation_records 生成拥有多个完整相关 Document 的开放推荐 Query。
def _recommendation_records(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    candidates = []
    for (category, ingredient), matches in _ingredient_index(profiles).items():
        if 2 <= len(matches) <= 10:
            candidates.append(
                {
                    "key": f"{category}:{ingredient}",
                    "category": category,
                    "ingredient": ingredient,
                    "profiles": sorted(matches, key=lambda profile: str(profile["source"])),
                }
            )
    selected = _balanced_key_select(candidates, QUOTAS["recommendation"], "recommendation")
    templates = (
        "想做会用到{ingredient}的{category}，有哪些选择？",
        "有哪些{category}会用到{ingredient}？",
        "我想找含{ingredient}的{category}，有啥推荐？",
    )
    records = []
    for index, item in enumerate(selected):
        query = templates[index % len(templates)].format(
            ingredient=item["ingredient"], category=CATEGORY_LABELS[item["category"]]
        )
        documents = []
        for profile in item["profiles"]:
            first = next((value for value in profile["ingredients"] if _valid_ingredient(value)), "")
            relevance = 3 if item["ingredient"] in profile["title"] or item["ingredient"] == first else 2
            documents.append(_document_label(profile, relevance))
        records.append(
            _base_record(
                "recommendation",
                query,
                str(item["key"]),
                str(item["category"]),
                documents,
                [],
                "hard",
                constraints=[
                    {"type": "required_ingredient", "value": item["ingredient"]},
                    {"type": "category", "value": item["category"]},
                ],
            )
        )
    return records


# _constraint_candidates 构造有正反候选的时间与工具限制组合。
def _constraint_candidates(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    values = []
    ingredient_index = _ingredient_index(profiles)
    for (category, ingredient), matches in ingredient_index.items():
        if not 2 <= len(matches) <= 14:
            continue
        for threshold in (15, 20, 30, 45, 60):
            eligible = [
                profile
                for profile in matches
                if profile["duration_minutes"] is not None and float(profile["duration_minutes"]) <= threshold
            ]
            excluded = [
                profile
                for profile in matches
                if profile["duration_minutes"] is not None and float(profile["duration_minutes"]) > threshold
            ]
            if 1 <= len(eligible) <= 8 and excluded:
                values.append(
                    {
                        "key": f"time:{category}:{ingredient}:{threshold}",
                        "kind": "max_minutes",
                        "category": category,
                        "ingredient": ingredient,
                        "value": threshold,
                        "profiles": eligible,
                    }
                )
        for tool in ("烤箱", "空气炸锅", "微波炉", "电饭煲"):
            eligible = [profile for profile in matches if tool not in profile["text"]]
            excluded = [profile for profile in matches if tool in profile["text"]]
            if 1 <= len(eligible) <= 8 and excluded:
                values.append(
                    {
                        "key": f"tool:{category}:{ingredient}:{tool}",
                        "kind": "forbidden_tool",
                        "category": category,
                        "ingredient": ingredient,
                        "value": tool,
                        "profiles": eligible,
                    }
                )
    return values


# _constraint_records 生成必须满足时间或厨房工具限制的多文档 Query。
def _constraint_records(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    candidates = _constraint_candidates(profiles)
    time_candidates = [item for item in candidates if item["kind"] == "max_minutes"]
    tool_candidates = [item for item in candidates if item["kind"] == "forbidden_tool"]
    selected = _balanced_key_select(time_candidates, 10, "constraint-time")
    selected += _balanced_key_select(tool_candidates, 10, "constraint-tool")
    records = []
    for item in selected:
        if item["kind"] == "max_minutes":
            query = (
                f"想做会用到{item['ingredient']}的{CATEGORY_LABELS[item['category']]}，"
                f"最好{item['value']}分钟内完成，有哪些选择？"
            )
            constraint = {"type": "max_minutes", "operator": "<=", "value": item["value"], "unit": "minute"}
        else:
            query = (
                f"想做会用到{item['ingredient']}的{CATEGORY_LABELS[item['category']]}，"
                f"但家里没有{item['value']}，有哪些做法？"
            )
            constraint = {"type": "forbidden_tool", "operator": "not_contains", "value": item["value"]}
        documents = [_document_label(profile, 3) for profile in sorted(item["profiles"], key=lambda p: p["source"])]
        records.append(
            _base_record(
                "constraint",
                query,
                str(item["key"]),
                str(item["category"]),
                documents,
                [],
                "hard",
                constraints=[
                    {"type": "required_ingredient", "value": item["ingredient"]},
                    {"type": "category", "value": item["category"]},
                    constraint,
                ],
            )
        )
    return records


# _unanswerable_records 生成与目标菜谱高度相似但语料没有医学依据的问题。
def _unanswerable_records(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    selected = _balanced_select(profiles, QUOTAS["unanswerable"], "unanswerable", lambda profile: True)
    templates = (
        "{title}的升糖指数具体是多少？",
        "糖尿病患者每天最多可以吃多少{title}？",
        "肾病患者食用{title}的安全摄入量是多少？",
        "{title}每份的嘌呤含量具体是多少毫克？",
        "孕妇每周最多可以吃几次{title}？",
        "{title}是否经过临床验证可以降低血压？",
        "高尿酸人群吃{title}的医学建议摄入量是多少？",
        "{title}每份含多少微克维生素D？",
        "婴儿最早几个月可以安全食用{title}？",
        "{title}对慢性肾病患者的推荐份量是多少？",
    )
    records = []
    for profile, template in zip(selected, templates):
        query = template.format(title=profile["title"])
        records.append(
            _base_record(
                "unanswerable",
                query,
                f"{profile['source']}:medical-unsupported",
                str(profile["category"]),
                [],
                [],
                "hard",
                answerable=False,
                primary_source=profile["source"],
                unanswerable_reason="菜谱语料不包含可支持该医学或人群摄入结论的证据",
            )
        )
    return records


# _inject_typo_variants 用少量共享 intent_id 的明确噪声变体测试错别字鲁棒性。
def _inject_typo_variants(records: List[Dict[str, Any]]) -> None:
    replacements = {
        "dish_lookup": ("怎么做", "怎么作"),
        "ingredient_fact": ("哪些材料", "那些材料"),
        "calculation_fact": ("海参", "海渗"),
        "procedure_fact": ("怎么操作", "怎么操做"),
        "cross_parent": ("怎么处理", "怎么处里"),
        "recommendation": ("有哪些选择", "有那些选择"),
        "constraint": ("分钟内", "分种内"),
    }
    for query_type, (original, typo) in replacements.items():
        indexes = [index for index, record in enumerate(records) if record["query_type"] == query_type]
        source_index = next((index for index in indexes if original in records[index]["query"]), None)
        if source_index is None or len(indexes) < 2:
            raise ValueError(f"无法为 {query_type} 构造错别字变体")
        source = records[source_index]
        target_index = next(
            index
            for index in indexes
            if index != source_index and records[index]["source_category"] == source["source_category"]
        )
        variant = copy.deepcopy(source)
        variant["query"] = str(source["query"]).replace(original, typo, 1)
        variant["query_id"] = _stable_id("q", query_type, source["intent_id"], variant["query"])
        variant["query_style"] = "typo"
        variant["query_tags"] = [query_type, "typo"]
        variant["variant_of_query_id"] = source["query_id"]
        records[target_index] = variant


# build_records 按固定配额生成完整 V4 Query 集。
def build_records(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    records = []
    records.extend(_dish_lookup_records(profiles))
    records.extend(_ingredient_fact_records(profiles))
    records.extend(_calculation_fact_records(profiles))
    records.extend(_procedure_fact_records(profiles))
    records.extend(_cross_parent_records(profiles))
    records.extend(_recommendation_records(profiles))
    records.extend(_constraint_records(profiles))
    records.extend(_unanswerable_records(profiles))
    _inject_typo_variants(records)
    return records


# validate_records 校验配额、层级归属、证据完整性和 Query 基本质量。
def validate_records(records: Sequence[Mapping[str, Any]], profiles: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    counts = Counter(str(record["query_type"]) for record in records)
    if dict(counts) != QUOTAS:
        raise ValueError(f"Query 配额不正确：expected={QUOTAS}, actual={dict(counts)}")
    if len({record["query_id"] for record in records}) != len(records):
        raise ValueError("query_id 不唯一")
    if len({record["query"] for record in records}) != len(records):
        raise ValueError("Query 文本不唯一")
    splits_by_intent: Dict[str, set[str]] = defaultdict(set)
    splits_by_source: Dict[str, set[str]] = defaultdict(set)
    for record in records:
        splits_by_intent[str(record["intent_id"])].add(str(record["dataset_split"]))
        if record.get("primary_source"):
            splits_by_source[str(record["primary_source"])].add(str(record["dataset_split"]))
    if any(len(splits) != 1 for splits in splits_by_intent.values()):
        raise ValueError("同一 intent_id 被分配到多个数据分区")
    if any(len(splits) != 1 for splits in splits_by_source.values()):
        raise ValueError("同一菜谱被分配到多个数据分区")

    document_ids = {int(profile["document_id"]) for profile in profiles}
    child_to_parent = {
        str(chunk["chunk_id"]): str(chunk["parent_id"])
        for profile in profiles
        for chunk in profile["chunks"]
    }
    child_to_document = {
        str(chunk["chunk_id"]): int(chunk["document_id"])
        for profile in profiles
        for chunk in profile["chunks"]
    }
    parent_to_document = {
        str(chunk["parent_id"]): int(chunk["document_id"])
        for profile in profiles
        for chunk in profile["chunks"]
    }
    evidence_types = {"ingredient_fact", "calculation_fact", "procedure_fact", "cross_parent"}
    for record in records:
        query = str(record["query"])
        query_type = str(record["query_type"])
        if not 4 <= len(query) <= 100 or any(phrase in query for phrase in FORBIDDEN_QUERY_PHRASES):
            raise ValueError(f"Query 文本不符合要求：{record['query_id']} {query}")
        relevant = record.get("relevant_documents") or []
        for document in relevant:
            if int(document["document_id"]) not in document_ids or not 1 <= int(document["relevance"]) <= 3:
                raise ValueError(f"文档标签无效：{record['query_id']}")
        groups = record.get("evidence_groups") or []
        if query_type in evidence_types and not groups:
            raise ValueError(f"证据型 Query 缺少 evidence_groups：{record['query_id']}")
        if query_type == "recommendation" and len(relevant) < 2:
            raise ValueError(f"推荐 Query 至少需要两个相关文档：{record['query_id']}")
        if query_type == "constraint" and (not relevant or not record.get("constraints")):
            raise ValueError(f"约束 Query 缺少相关文档或约束：{record['query_id']}")
        if query_type == "unanswerable" and (record.get("answerable", True) or relevant or groups):
            raise ValueError(f"无答案 Query 不应包含正例：{record['query_id']}")

        group_parent_ids = set()
        relevant_document_ids = {int(document["document_id"]) for document in relevant}
        for group in groups:
            child_ids = [str(value) for value in group.get("acceptable_child_ids") or []]
            parent_ids = [str(value) for value in group.get("acceptable_parent_ids") or []]
            if not child_ids or not parent_ids:
                raise ValueError(f"证据组缺少 Parent/Child：{record['query_id']}")
            if any(value not in child_to_parent for value in child_ids):
                raise ValueError(f"证据组引用不存在的 Child：{record['query_id']}")
            if any(value not in parent_to_document for value in parent_ids):
                raise ValueError(f"证据组引用不存在的 Parent：{record['query_id']}")
            if any(child_to_parent[value] not in parent_ids for value in child_ids):
                raise ValueError(f"Child 不属于证据组 Parent：{record['query_id']}")
            if any(child_to_document[value] not in relevant_document_ids for value in child_ids):
                raise ValueError(f"证据 Child 不属于相关文档：{record['query_id']}")
            group_parent_ids.update(parent_ids)
        if query_type == "cross_parent" and len(group_parent_ids) < 2:
            raise ValueError(f"跨 Parent Query 未覆盖两个 Parent：{record['query_id']}")

    return {
        "query_count": len(records),
        "query_type_counts": dict(counts),
        "source_count": len(
            {
                document["source"]
                for record in records
                for document in record.get("relevant_documents") or []
            }
        ),
        "category_counts": dict(Counter(str(record["source_category"]) for record in records)),
        "split_counts": dict(Counter(str(record["dataset_split"]) for record in records)),
        "label_status_counts": dict(Counter(str(record["label_status"]) for record in records)),
        "query_style_counts": dict(Counter(str(record["query_style"]) for record in records)),
        "retrieval_scope_counts": dict(Counter(str(record["retrieval_scope"]) for record in records)),
        "parent_child_count_bucket_counts": dict(
            Counter(str(record["parent_child_count_bucket"]) for record in records)
        ),
    }


# build_chunk_gold 从证据组生成独立的 Child Chunk qrels，保留 overlap 等价块的严格 ID 标签。
def build_chunk_gold(
    records: Sequence[Mapping[str, Any]],
    profiles: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    chunks_by_id = {
        str(chunk["chunk_id"]): chunk
        for profile in profiles
        for chunk in profile["chunks"]
    }
    output = []
    for record in records:
        groups = [group for group in record.get("evidence_groups") or [] if group.get("required", True)]
        if not groups:
            continue

        judgments: Dict[str, Dict[str, Any]] = {}
        ordered_child_ids = []
        for group in groups:
            group_id = str(group["group_id"])
            for raw_child_id in group.get("acceptable_child_ids") or []:
                child_id = str(raw_child_id)
                chunk = chunks_by_id[child_id]
                if child_id not in judgments:
                    ordered_child_ids.append(child_id)
                    judgments[child_id] = {
                        "chunk_id": child_id,
                        "document_id": int(chunk["document_id"]),
                        "parent_id": str(chunk["parent_id"]),
                        "source": str(chunk["source"]),
                        "relevance": 3,
                        "evidence_group_ids": [],
                    }
                judgments[child_id]["evidence_group_ids"].append(group_id)

        output.append(
            {
                "query_id": str(record["query_id"]),
                "intent_id": str(record["intent_id"]),
                "query_type": str(record["query_type"]),
                "dataset_split": str(record["dataset_split"]),
                "gold_scope": "child_chunk",
                "relevant_child_ids": ordered_child_ids,
                "judgments": [judgments[child_id] for child_id in ordered_child_ids],
                "label_status": str(record["label_status"]),
                "generation_method": "derived_from_reviewable_evidence_groups",
            }
        )
    return output


# validate_chunk_gold 校验严格 Chunk qrels 与 Query 证据组及语料映射完全一致。
def validate_chunk_gold(
    chunk_gold: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    profiles: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    records_by_id = {str(record["query_id"]): record for record in records}
    if len(records_by_id) != len(records):
        raise ValueError("Chunk Gold 无法关联重复 query_id")
    if len({str(item["query_id"]) for item in chunk_gold}) != len(chunk_gold):
        raise ValueError("Chunk Gold query_id 不唯一")

    chunks_by_id = {
        str(chunk["chunk_id"]): chunk
        for profile in profiles
        for chunk in profile["chunks"]
    }
    evidence_query_ids = {
        str(record["query_id"])
        for record in records
        if any(group.get("required", True) for group in record.get("evidence_groups") or [])
    }
    gold_query_ids = {str(item["query_id"]) for item in chunk_gold}
    if gold_query_ids != evidence_query_ids:
        missing = sorted(evidence_query_ids - gold_query_ids)
        extra = sorted(gold_query_ids - evidence_query_ids)
        raise ValueError(f"Chunk Gold 覆盖范围不正确：missing={missing[:3]}, extra={extra[:3]}")

    judgment_count = 0
    for item in chunk_gold:
        query_id = str(item["query_id"])
        record = records_by_id[query_id]
        if item.get("gold_scope") != "child_chunk":
            raise ValueError(f"Chunk Gold scope 无效：{query_id}")
        for field in ("intent_id", "query_type", "dataset_split", "label_status"):
            if str(item.get(field)) != str(record.get(field)):
                raise ValueError(f"Chunk Gold 字段与 Query 不一致：{query_id} {field}")

        relevant_child_ids = [str(value) for value in item.get("relevant_child_ids") or []]
        judgments = item.get("judgments") or []
        judgment_ids = [str(judgment.get("chunk_id")) for judgment in judgments]
        if not relevant_child_ids or len(relevant_child_ids) != len(set(relevant_child_ids)):
            raise ValueError(f"Chunk Gold 缺少正例或包含重复 Child：{query_id}")
        if judgment_ids != relevant_child_ids:
            raise ValueError(f"Chunk Gold judgments 与 relevant_child_ids 不一致：{query_id}")

        groups = [group for group in record.get("evidence_groups") or [] if group.get("required", True)]
        groups_by_id = {str(group["group_id"]): group for group in groups}
        expected_child_ids = list(
            dict.fromkeys(
                str(child_id)
                for group in groups
                for child_id in group.get("acceptable_child_ids") or []
            )
        )
        if relevant_child_ids != expected_child_ids:
            raise ValueError(f"Chunk Gold 未严格覆盖证据组 Child：{query_id}")

        for judgment in judgments:
            child_id = str(judgment["chunk_id"])
            chunk = chunks_by_id.get(child_id)
            if chunk is None:
                raise ValueError(f"Chunk Gold 引用不存在的 Child：{query_id} {child_id}")
            if not 1 <= int(judgment.get("relevance", 0)) <= 3:
                raise ValueError(f"Chunk Gold relevance 无效：{query_id} {child_id}")
            if (
                int(judgment.get("document_id")) != int(chunk["document_id"])
                or str(judgment.get("parent_id")) != str(chunk["parent_id"])
                or str(judgment.get("source")) != str(chunk["source"])
            ):
                raise ValueError(f"Chunk Gold 层级归属错误：{query_id} {child_id}")
            group_ids = [str(value) for value in judgment.get("evidence_group_ids") or []]
            if not group_ids or any(group_id not in groups_by_id for group_id in group_ids):
                raise ValueError(f"Chunk Gold 缺少有效 evidence_group_id：{query_id} {child_id}")
            if any(child_id not in groups_by_id[group_id]["acceptable_child_ids"] for group_id in group_ids):
                raise ValueError(f"Chunk Gold 与证据组 Child 关系不一致：{query_id} {child_id}")
        judgment_count += len(judgments)

    return {
        "chunk_gold_query_count": len(chunk_gold),
        "chunk_gold_judgment_count": judgment_count,
        "chunk_gold_label_status_counts": dict(
            Counter(str(item["label_status"]) for item in chunk_gold)
        ),
    }


# _write_jsonl 以稳定字段顺序写出可版本控制的 Query 数据集。
def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> str:
    lines = [json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records]
    payload = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# main 生成 Query、执行结构校验并写出可追踪的 Manifest。
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, default=Path("tests/evaluation-version1/datasets/raw/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("tests/evaluation-version4/datasets/queries.jsonl"))
    parser.add_argument("--chunk-gold-output", type=Path, default=Path("tests/evaluation-version4/datasets/chunk_gold.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("tests/evaluation-version4/datasets/manifest.json"))
    args = parser.parse_args()

    profiles = _load_profiles(args.mapping)
    records = build_records(profiles)
    validation = validate_records(records, profiles)
    chunk_gold = build_chunk_gold(records, profiles)
    chunk_gold_validation = validate_chunk_gold(chunk_gold, records, profiles)
    dataset_sha256 = _write_jsonl(args.output, records)
    chunk_gold_sha256 = _write_jsonl(args.chunk_gold_output, chunk_gold)
    mapping_sha256 = hashlib.sha256(args.mapping.read_bytes()).hexdigest()
    manifest = {
        "dataset_version": "retrieval-evaluation-v4",
        "corpus_mapping": str(args.mapping),
        "corpus_mapping_sha256": mapping_sha256,
        "dataset_sha256": dataset_sha256,
        "chunk_gold_file": str(args.chunk_gold_output),
        "chunk_gold_sha256": chunk_gold_sha256,
        "quotas": QUOTAS,
        **validation,
        **chunk_gold_validation,
        "review_policy": "自动结构校验已完成；正式基准测试前必须逐条人工确认并改为 reviewed",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
