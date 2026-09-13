"""Generate an auditable retrieval evaluation set from imported recipe chunks.

The generator deliberately uses deterministic templates and evidence from the
source Markdown. It does not call an LLM, so every label can be checked back
against a concrete chunk before the JSONL is written.
"""

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


CATEGORY_ORDER = (
    "meat_dish",
    "vegetable_dish",
    "staple",
    "aquatic",
    "breakfast",
    "soup",
)
CATEGORY_LABELS = {
    "meat_dish": "家常肉菜",
    "vegetable_dish": "蔬菜菜肴",
    "staple": "主食",
    "aquatic": "海鲜菜",
    "breakfast": "早餐",
    "soup": "汤品",
}
GENERIC_INGREDIENTS = {
    "水", "清水", "开水", "油", "食用油", "植物油", "盐", "食用盐",
    "糖", "白糖", "白砂糖", "生抽", "酱油", "料酒", "胡椒粉", "黑胡椒粉",
    "白胡椒粉", "淀粉", "玉米淀粉", "生粉", "鸡精", "味精", "醋", "白醋",
    "陈醋", "香醋", "香油", "花椒油", "蚝油", "豆瓣酱", "番茄酱", "蒸鱼豉油",
    "菜籽油", "食用植物油", "五香粉", "孜然粉", "孜然", "椒盐粉", "辣椒粉",
    "辣椒油", "香料", "综合香料粉", "调味料", "调味粉",
}
TOOL_MARKERS = (
    "锅", "碗", "盘", "盆", "刀", "砧板", "蒸笼", "蒸锅", "微波炉",
    "烤箱", "空气炸锅", "面包机", "勺", "杯", "手套", "纸", "滤网",
    "过滤网", "打火机", "搅拌器", "电饼铛", "容器", "冰箱", "冰柜",
    "保鲜膜", "筷子", "剪刀", "削皮刀", "烤篮", "喷壶", "擀面杖", "汤匙", "茶匙",
)
METHOD_TERMS = (
    "油炸", "煎", "蒸", "炒", "炖", "煮", "烤", "微波", "焯", "腌制",
    "腌", "卤", "拌", "勾芡", "收汁", "冷藏",
)
COOKING_METHOD_TERMS = ("油炸", "炸", "煎", "炒", "蒸", "炖", "煮", "烧开", "烤", "微波", "拌", "勾芡", "收汁")
FORBIDDEN_INGREDIENTS = (
    "辣椒", "花生", "香菜", "芝麻", "牛奶", "鸡蛋", "葱", "蒜", "姜",
    "黄油", "芥末", "椰浆", "番茄", "豆腐", "面粉", "香菇",
)
FORBIDDEN_METHODS = ("油炸", "煎", "蒸", "烤", "微波", "炖", "焯", "腌制", "勾芡")
TASTE_TERMS = (
    "清淡", "鲜美", "鲜嫩", "香辣", "酸甜", "咸鲜", "浓郁", "酥脆", "软糯",
    "爽滑", "开胃", "下饭", "快手", "聚餐", "早餐", "下午茶", "夏日", "新手",
)
STATE_TERMS = (
    "金黄", "焦香", "断生", "凝固", "软烂", "浓稠", "熟透", "冒泡", "上色",
    "浮起", "微焦", "收汁", "入味", "成型",
)


def normalize(text):
    return re.sub(r"[\s\u3000，。、“”‘’：:；;、（）()【】\[\]!?！？\-—_/]", "", text.lower())


def stable_id(source, query):
    return hashlib.sha1((source + "\n" + query).encode("utf-8")).hexdigest()[:16]


def section_text(text, heading):
    """Return the body below a level-2 Markdown heading."""
    pattern = rf"(?ms)^##\s+{re.escape(heading)}\s*(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def bullet_lines(text):
    return [
        re.sub(r"^\s*[-*+]\s*", "", line).strip()
        for line in text.splitlines()
        if re.match(r"^\s*[-*+]\s+", line) and len(line.strip()) > 2
    ]


def clean_ingredient(line):
    value = re.sub(r"\s+", "", line)
    value = re.sub(r"[（(].*?[）)]", "", value)
    value = re.sub(r"^\d+(?:\.\d+)?(?:袋|份)\s*", "", value)
    value = re.sub(r"\d+(?:\.\d+)?\s*(?:毫升|ml|升|l|克|g|公斤|kg|斤|分钟|分|℃|°C)", "", value, flags=re.I)
    value = re.split(r"(?:可用|可以|参见|建议|推荐|再次|需要|操作时)", value, maxsplit=1)[0]
    value = re.sub(r"^(?:可选|备用|调料|工具)[:：]?", "", value)
    if "：" in value or ":" in value:
        value = re.split(r"[：:]", value, maxsplit=1)[1]
    value = re.split(r"[，,。；;、]", value, maxsplit=1)[0]
    value = value.split("—", 1)[0].split("-", 1)[0]
    return value.strip("。；;，,")


def extract_title(source, rows):
    for row in sorted(rows, key=lambda item: item.get("chunk_index", 0)):
        match = re.search(r"(?m)^#\s+(.+?)\s*$", row.get("content", ""))
        if match:
            title = match.group(1).strip()
            title = re.sub(r"\s*[-－]?预览图.*$", "", title)
            return re.sub(r"的做法$", "", title).strip()
    return Path(source).stem


def collect_profile(source, rows):
    rows = sorted(rows, key=lambda item: item.get("chunk_index", 0))
    text = "\n".join(row.get("content", "") for row in rows)
    ingredient_values = []
    for row in rows:
        body = section_text(row.get("content", ""), "必备原料和工具")
        for line in bullet_lines(body):
            value = clean_ingredient(line)
            if not value or any(marker in value for marker in TOOL_MARKERS):
                continue
            if value not in ingredient_values and len(value) <= 18:
                ingredient_values.append(value)
    if not ingredient_values:
        for row in rows:
            for line in bullet_lines(row.get("content", "")):
                value = clean_ingredient(line)
                if value and not any(marker in value for marker in TOOL_MARKERS) and len(value) <= 18:
                    if value not in ingredient_values:
                        ingredient_values.append(value)
    overview = ""
    for row in rows:
        content = row.get("content", "")
        if "预估卡路里" in content or "预估烹饪难度" in content:
            overview = content.split("## 必备原料和工具", 1)[0]
            break
    operation_lines = []
    for row in rows:
        body = section_text(row.get("content", ""), "操作")
        operation_lines.extend(bullet_lines(body))
    if not operation_lines:
        # Parent-child chunking often leaves an empty ``## 操作`` parent and
        # puts the actual bullets in following ``###`` child chunks.
        in_operation = False
        for row in rows:
            content = row.get("content", "")
            if re.search(r"(?m)^##\s+操作\s*$", content):
                in_operation = True
            if in_operation:
                operation_lines.extend(bullet_lines(content))
            if in_operation and re.search(r"(?m)^##\s+附加内容\s*$", content):
                in_operation = False
    operation_lines = list(dict.fromkeys(operation_lines))
    return {
        "source": source,
        "category": source.split("/", 1)[0],
        "title": extract_title(source, rows),
        "rows": rows,
        "text": text,
        "normalized_text": normalize(text),
        "ingredients": ingredient_values,
        "overview": overview,
        "operations": operation_lines,
    }


def best_chunk(profile, predicate, fallback=True):
    candidates = [row for row in profile["rows"] if predicate(row.get("content", ""))]
    if candidates:
        return max(candidates, key=lambda row: (len(row.get("content", "")), -row.get("chunk_index", 0)))
    return profile["rows"][0] if fallback else None


def ingredient_chunk(profile, anchor=None):
    return best_chunk(profile, lambda content: "## 必备原料和工具" in content and (not anchor or anchor in content))


def operation_chunk(profile, anchor=None):
    operation_rows = []
    in_operation = False
    for row in profile["rows"]:
        content = row.get("content", "")
        if re.search(r"(?m)^##\s+操作\s*$", content):
            in_operation = True
        if in_operation and not re.search(r"(?m)^##\s+附加内容\s*$", content):
            operation_rows.append(row)
        if in_operation and re.search(r"(?m)^##\s+附加内容\s*$", content):
            in_operation = False
    if operation_rows:
        anchored = [row for row in operation_rows if not anchor or anchor in row.get("content", "")]
        candidates = anchored or operation_rows
        return max(
            candidates,
            key=lambda row: (
                bool(bullet_lines(row.get("content", ""))),
                any(term in row.get("content", "") for term in COOKING_METHOD_TERMS),
                len(row.get("content", "")),
            ),
        )
    return best_chunk(profile, lambda content: any(term in content for term in METHOD_TERMS) and (not anchor or anchor in content))


def overview_chunk(profile):
    return best_chunk(profile, lambda content: "预估卡路里" in content or "预估烹饪难度" in content)


def choose_anchors(profile, count=2):
    values = [
        value for value in profile["ingredients"]
        if value not in GENERIC_INGREDIENTS and len(value) >= 2 and not value.isdigit() and re.search(r"[一-龥]", value)
    ]
    # Keep non-title query types from accidentally turning an ingredient such
    # as “牛排酱汁” into a disguised title lookup for “牛排”.
    safe_values = [value for value in values if profile["title"] not in value]
    if safe_values:
        values = safe_values
    if not values:
        values = [value for value in profile["ingredients"] if len(value) >= 1 and profile["title"] not in value and re.search(r"[一-龥]", value)]
    values = sorted(values, key=lambda value: (-len(value), profile["ingredients"].index(value)))
    return values[:count] or [CATEGORY_LABELS[profile["category"]]]


def taste_phrase(profile):
    matches = [term for term in TASTE_TERMS if term in profile["overview"] or term in profile["text"]]
    if matches:
        return "、".join(matches[:2])
    defaults = {
        "meat_dish": "咸香下饭", "vegetable_dish": "清爽家常", "staple": "饱腹方便",
        "aquatic": "鲜嫩清鲜", "breakfast": "快手早餐", "soup": "清淡鲜美",
    }
    return defaults.get(profile["category"], "家常风味")


def clean_action(value):
    value = re.sub(r"[（(].*?[）)]", "", value)
    value = re.sub(r"\s+", "", value).strip("。；;，,")
    value = re.sub(r"^(?:步骤?\s*\d+[：:]?|\d+[、.)])", "", value)
    return value.strip("：:")[:42]


def semantic_query(profile, anchors):
    operation_text = "。".join(profile["operations"])
    method = next((term for term in COOKING_METHOD_TERMS if term in operation_text), None)
    method_phrases = {
        "油炸": "炸至表面上色",
        "炸": "炸至表面上色",
        "煎": "煎至两面金黄",
        "炒": "翻炒至断生",
        "蒸": "蒸至熟透",
        "炖": "小火炖至软烂",
        "煮": "煮至熟透",
        "烧开": "加热至沸腾",
        "烤": "烤至表面金黄",
        "微波": "用微波加热至凝固",
        "拌": "拌匀并使味道融合",
        "勾芡": "勾芡至汤汁浓稠",
        "收汁": "收汁至汤汁浓稠",
    }
    action = method_phrases.get(method, "加热至熟透并完成调味")
    state = next((term for term in STATE_TERMS if term in operation_text), "熟透入味")
    return f"先处理{anchors[0]}并完成切配，再{action}，直到{state}，这种{CATEGORY_LABELS[profile['category']]}的具体步骤是什么？"


def numeric_measurements(profile):
    """Extract values and the chunk that provides evidence for them."""
    fields = []
    range_patterns = (
        ("temperature_c", re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|~|～|至|到)\s*(\d+(?:\.\d+)?)\s*(?:℃|°C|摄氏度|度)", re.I), "celsius"),
        ("minutes", re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|~|～|至|到)\s*(\d+(?:\.\d+)?)\s*(分钟|分|小时|h)", re.I), "time"),
    )
    duration_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*小时\s*(\d+(?:\.\d+)?)\s*(分钟|分)", re.I)
    single_patterns = (
        ("calories", re.compile(r"预估卡路里\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(大卡|千卡|卡路里)", re.I), "calories"),
        ("temperature_c", re.compile(r"(\d+(?:\.\d+)?)\s*(?:℃|°C|摄氏度|度)", re.I), "celsius"),
        ("minutes", re.compile(r"(\d+(?:\.\d+)?)\s*(分钟|分|小时|h)", re.I), "time"),
        ("grams", re.compile(r"(\d+(?:\.\d+)?)\s*(克|g|公斤|kg|斤)", re.I), "mass"),
        ("milliliters", re.compile(r"(\d+(?:\.\d+)?)\s*(毫升|ml|升|l)", re.I), "volume"),
    )
    for profile_row in profile["rows"]:
        content = profile_row.get("content", "")
        for match in duration_pattern.finditer(content):
            hours, minutes = float(match.group(1)), float(match.group(2))
            fields.append({"field": "minutes", "operator": "<=", "value": hours * 60 + minutes, "unit": "minute", "source_value": match.group(0), "chunk": profile_row})
        for field, pattern, kind in range_patterns:
            for match in pattern.finditer(content):
                left, right = float(match.group(1)), float(match.group(2))
                if kind == "time" and match.group(3) in ("小时", "h"):
                    left, right = left * 60, right * 60
                source_unit = match.group(3) if match.lastindex and match.lastindex >= 3 else "度"
                fields.append({"field": field, "operator": "between", "min": min(left, right), "max": max(left, right), "unit": "minute" if field == "minutes" else "celsius", "source_min": match.group(1), "source_max": match.group(2), "source_unit": source_unit, "chunk": profile_row})
        for field, pattern, kind in single_patterns:
            for match in pattern.finditer(content):
                value = float(match.group(1))
                unit = match.group(2) if match.lastindex and match.lastindex >= 2 else "度"
                if kind == "time" and unit in ("小时", "h"):
                    value *= 60
                if kind == "mass" and unit in ("公斤", "kg"):
                    value *= 1000
                elif kind == "mass" and unit == "斤":
                    value *= 500
                elif kind == "volume" and unit in ("升", "l"):
                    value *= 1000
                operator = "<=" if field == "minutes" else "eq"
                fields.append({"field": field, "operator": operator, "value": value, "unit": {"calories": "kcal", "temperature_c": "celsius", "minutes": "minute", "grams": "gram", "milliliters": "milliliter"}[field], "source_value": match.group(1), "source_unit": unit, "chunk": profile_row})
    unique = {}
    for item in fields:
        unique.setdefault(item["field"], item)
    return list(unique.values())


def number_text(value):
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def numeric_query(profile, anchors, measurement):
    field = measurement["field"]
    anchor = anchors[0]
    if measurement["operator"] == "between":
        low, high = number_text(measurement["min"]), number_text(measurement["max"])
        if field == "minutes":
            return f"以{anchor}为主、总用时在{low}到{high}分钟之间的做法怎么安排？"
        return f"处理{anchor}时，温度控制在{low}到{high}摄氏度的做法是什么？"
    value = number_text(measurement["value"])
    display_value = str(measurement.get("source_value", value)).replace(" ", "") if field == "minutes" else value
    if field == "minutes" and not re.search(r"分钟|分|小时|h", display_value, re.I):
        display_value += "分钟"
    templates = {
        "minutes": f"有没有以{anchor}为主、总用时不超过{display_value}的{CATEGORY_LABELS[profile['category']]}？步骤怎么做？",
        "temperature_c": f"处理{anchor}时，需要控制在约{value}摄氏度的做法怎么做？",
        "grams": f"{anchor}用量约为{value}克的做法，具体备料和步骤是什么？",
        "milliliters": f"需要加入约{value}毫升液体、以{anchor}为主的做法怎么安排？",
        "calories": f"有没有每份约{value}大卡、以{anchor}为主的{CATEGORY_LABELS[profile['category']]}？",
    }
    return templates[field]


def choose_forbidden(profile, term_counts, prefer_method=False):
    normalized = profile["normalized_text"]
    if prefer_method:
        method_candidates = [term for term in FORBIDDEN_METHODS if normalize(term) not in normalized]
        if method_candidates:
            term = max(method_candidates, key=lambda value: (term_counts[value], len(value)))
            return term, "method_exclusion"
    ingredient_candidates = [
        term for term in FORBIDDEN_INGREDIENTS
        if normalize(term) not in normalized and term not in profile["ingredients"]
    ]
    if ingredient_candidates:
        term = max(ingredient_candidates, key=lambda value: (term_counts[value], len(value)))
        return term, "ingredient_absence"
    method_candidates = [term for term in FORBIDDEN_METHODS if normalize(term) not in normalized]
    if method_candidates:
        term = max(method_candidates, key=lambda value: (term_counts[value], len(value)))
        return term, "method_exclusion"
    return "花椒", "ingredient_absence"


def query_record(profile, query, query_type, chunks, hard_negatives, **extra):
    row = {
        "query_id": stable_id(profile["source"], query),
        "query": query,
        "query_type": query_type,
        "query_tags": [query_type],
        "source": profile["source"],
        "source_category": profile["category"],
        "positive_documents": [profile["document_id"]],
        "positive_chunks": list(dict.fromkeys(chunk["chunk_id"] for chunk in chunks if chunk)),
        "hard_negative_documents": [item["document_id"] for item in hard_negatives],
        "hard_negative_reasons": [item["reason"] for item in hard_negatives],
        "forbidden_terms": [],
        "constraint_type": None,
        "numeric_constraints": [],
        "label_status": "needs_review",
    }
    row.update(extra)
    return row


def profile_tokens(profile):
    tokens = set()
    for ingredient in profile["ingredients"]:
        value = normalize(ingredient)
        if len(value) >= 2:
            tokens.add(value)
    for term in METHOD_TERMS:
        if term in profile["text"]:
            tokens.add(term)
    return tokens


def choose_hard_negatives(profile, profiles, query_type, anchor=None, forbidden=None, measurement=None):
    target_tokens = profile_tokens(profile)
    scored = []
    for candidate in profiles:
        if candidate["document_id"] == profile["document_id"]:
            continue
        shared = sorted(target_tokens & profile_tokens(candidate), key=lambda value: (-len(value), value))
        score = len(shared) * 4
        reasons = []
        if candidate["category"] == profile["category"]:
            score += 3
            reasons.append("same_category")
        if anchor and anchor in candidate["text"]:
            score += 5
            reasons.append(f"shared_ingredient:{anchor}")
        if forbidden and forbidden in candidate["text"]:
            score += 4
            reasons.append(f"contains_forbidden:{forbidden}")
        if shared:
            reasons.append("shared_terms:" + ",".join(shared[:3]))
        if query_type == "numeric" and measurement:
            if any(item["field"] == measurement["field"] for item in numeric_measurements(candidate)):
                score += 1
                reasons.append(f"same_numeric_field:{measurement['field']}")
        scored.append((score, candidate["category"] != profile["category"], candidate["source"], candidate, reasons or ["nearest_profile"]))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [{"document_id": item[3]["document_id"], "reason": ";".join(item[4])} for item in scored[:2]]


def source_richness(profile):
    return (bool(profile["ingredients"]), bool(profile["operations"]), bool(profile["overview"]), len(numeric_measurements(profile)), len(profile["text"]))


def load_profiles(mapping):
    groups = defaultdict(list)
    for line in mapping.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            groups[row["source"]].append(row)
    profiles = []
    for source, rows in sorted(groups.items()):
        profile = collect_profile(source, rows)
        profile["document_id"] = rows[0]["document_id"]
        profiles.append(profile)
    return profiles


def build_records(profiles, sources_per_category):
    term_counts = Counter()
    for profile in profiles:
        for term in FORBIDDEN_INGREDIENTS + FORBIDDEN_METHODS:
            if normalize(term) in profile["normalized_text"]:
                term_counts[term] += 1
    selected = []
    for category in CATEGORY_ORDER:
        candidates = [profile for profile in profiles if profile["category"] == category]
        candidates.sort(key=lambda item: (-source_richness(item)[3], -len(item["text"]), item["source"]))
        selected.extend(candidates[:sources_per_category])
    if len(selected) < sources_per_category * len(CATEGORY_ORDER):
        raise ValueError("not enough sources in one of the requested categories")

    records = []
    field_order = ("minutes", "temperature_c", "grams", "milliliters", "calories")
    for profile_index, profile in enumerate(selected):
        anchors = choose_anchors(profile)
        anchor_text = "、".join(anchors)
        dish_query = f"请给出{profile['title']}的完整用料和关键步骤。"
        records.append(query_record(profile, dish_query, "dish_name", [ingredient_chunk(profile, anchors[0]), operation_chunk(profile, anchors[0])], choose_hard_negatives(profile, profiles, "dish_name", anchor=anchors[0])))

        ingredient_query = f"家里有{anchor_text}，想做一道{CATEGORY_LABELS[profile['category']]}，应该怎样准备和烹饪？"
        records.append(query_record(profile, ingredient_query, "ingredient", [ingredient_chunk(profile, anchors[0]), operation_chunk(profile, anchors[0])], choose_hard_negatives(profile, profiles, "ingredient", anchor=anchors[0])))

        taste_query = f"想吃{taste_phrase(profile)}、以{anchors[0]}为主的{CATEGORY_LABELS[profile['category']]}，有什么具体做法？"
        records.append(query_record(profile, taste_query, "taste_scene", [overview_chunk(profile), operation_chunk(profile, anchors[0])], choose_hard_negatives(profile, profiles, "taste_scene", anchor=anchors[0])))

        semantic = semantic_query(profile, anchors)
        records.append(query_record(profile, semantic, "semantic_description", [operation_chunk(profile), overview_chunk(profile)], choose_hard_negatives(profile, profiles, "semantic_description", anchor=anchors[0])))

        forbidden, constraint_type = choose_forbidden(profile, term_counts, prefer_method=profile_index % 4 == 0)
        negative_query = f"用{anchors[0]}做一道不含{forbidden}的{taste_phrase(profile)}{CATEGORY_LABELS[profile['category']]}，步骤怎么安排？"
        records.append(query_record(profile, negative_query, "negative", [ingredient_chunk(profile, anchors[0]), operation_chunk(profile, anchors[0])], choose_hard_negatives(profile, profiles, "negative", anchor=anchors[0], forbidden=forbidden), query_tags=["negative", constraint_type], forbidden_terms=[forbidden], constraint_type=constraint_type))

        measurements = numeric_measurements(profile)
        if not measurements:
            raise ValueError(f"source has no numeric evidence: {profile['source']}")
        available = {item["field"]: item for item in measurements}
        measurement = next(
            (available[field_order[(profile_index + offset) % len(field_order)]] for offset in range(len(field_order)) if field_order[(profile_index + offset) % len(field_order)] in available),
            measurements[0],
        )
        numeric_constraints = [{key: value for key, value in measurement.items() if key != "chunk"}]
        numeric = numeric_query(profile, anchors, measurement)
        records.append(query_record(profile, numeric, "numeric", [measurement["chunk"], ingredient_chunk(profile, anchors[0])], choose_hard_negatives(profile, profiles, "numeric", anchor=anchors[0], measurement=measurement), query_tags=["numeric", measurement["field"]], numeric_constraints=numeric_constraints))
    return records, selected


def validate(records, profiles):
    sources = {row["source"] for row in records}
    categories = {row["source_category"] for row in records}
    counts = Counter(row["query_type"] for row in records)
    expected_types = {"dish_name", "ingredient", "taste_scene", "semantic_description", "negative", "numeric"}
    if len(sources) < 100 or len(categories) < 6:
        raise ValueError(f"coverage check failed: sources={len(sources)} categories={len(categories)}")
    if set(counts) != expected_types or len(set(counts.values())) != 1:
        raise ValueError(f"type balance check failed: {counts}")
    by_source = {profile["source"]: profile for profile in profiles}
    by_chunk = {row["chunk_id"]: row for profile in profiles for row in profile["rows"]}
    for row in records:
        profile = by_source[row["source"]]
        if row["query_type"] != "dish_name" and profile["title"] in row["query"]:
            raise ValueError(f"non-title query contains target title: {row['query_id']}")
        if row["query_type"] == "dish_name" and profile["title"] not in row["query"]:
            raise ValueError(f"title query lost title: {row['query_id']}")
        if row["positive_documents"] != [profile["document_id"]]:
            raise ValueError(f"document label mismatch: {row['query_id']}")
        for chunk_id in row["positive_chunks"]:
            if chunk_id not in by_chunk or by_chunk[chunk_id]["document_id"] != profile["document_id"]:
                raise ValueError(f"chunk label mismatch: {row['query_id']}")
        if set(row["positive_documents"]) & set(row["hard_negative_documents"]):
            raise ValueError(f"hard negative overlaps positive: {row['query_id']}")
        if row["query_type"] == "negative" and any(normalize(term) in profile["normalized_text"] for term in row["forbidden_terms"]):
            raise ValueError(f"forbidden term appears in positive source: {row['query_id']}")
        if row["query_type"] == "numeric":
            for constraint in row["numeric_constraints"]:
                value = constraint.get("value")
                source_value = str(constraint.get("source_value", ""))
                normalized_contents = [
                    re.sub(r"\s+", "", by_chunk[chunk_id]["content"])
                    for chunk_id in row["positive_chunks"]
                ]
                evidence_found = any(
                    (source_value and source_value.replace(" ", "") in content)
                    or (value is not None and number_text(value) in content)
                    for content in normalized_contents
                )
                if constraint.get("operator") == "between":
                    evidence_found = all(
                        any(str(constraint.get(key, "")).replace(" ", "") in content for content in normalized_contents)
                        for key in ("source_min", "source_max")
                    )
                if value is not None and not evidence_found:
                    raise ValueError(f"numeric evidence missing: {row['query_id']}")
                if constraint.get("operator") == "between" and not evidence_found:
                    raise ValueError(f"numeric range evidence missing: {row['query_id']}")
    print(f"validated sources={len(sources)} categories={len(categories)} queries={len(records)} types={dict(counts)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping", type=Path, default=Path("evaluation/datasets/raw/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/datasets/labels/queries.jsonl"))
    parser.add_argument("--sources-per-category", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None, help="optional compatibility limit applied after validation")
    args = parser.parse_args()
    profiles = load_profiles(args.mapping)
    records, _ = build_records(profiles, args.sources_per_category)
    validate(records, profiles)
    if args.limit is not None:
        records = records[: args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"output={args.output} queries={len(records)} sources={len({r['source'] for r in records})}")


if __name__ == "__main__":
    main()
