"""Create a stronger, semantically equivalent noisy query set.

Only the ``query`` field is changed. Labels, document/chunk ids, forbidden
terms, numeric constraints and query ids are copied verbatim from the source
JSONL file. The generated samples are intended to exercise query rewriting,
not merely punctuation robustness.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path


TYPO_REPLACEMENTS = (
    ("关键", "关健"),
    ("步骤", "步奏"),
    ("烹饪", "烹任"),
    ("具体", "具休"),
    ("控制", "控止"),
    ("加入", "加如"),
    ("处理", "处里"),
    ("切配", "切佩"),
    # A traditional-form error is useful for numeric queries that have no
    # other generic word available, while leaving the number and unit intact.
    ("约", "約"),
)

# Common colloquial and regional alternatives. Food aliases are intentionally
# limited to near-synonyms so the query remains about the same ingredient.
FOOD_DIALECT_REPLACEMENTS = (
    ("土豆", "洋芋"),
    ("土豆", "洋山芋"),
    ("玉米", "苞谷"),
    ("玉米", "包谷"),
    ("番茄", "西红柿"),
    ("西红柿", "番茄"),
    ("红薯", "地瓜"),
    ("鸡蛋", "鸡子儿"),
    ("鸡蛋", "鸡蛋儿"),
    ("馒头", "馍"),
    ("面条", "面条子"),
    ("面条", "面儿"),
)

DIALECT_REPLACEMENTS = (
    ("请给出", "麻烦说下"),
    ("请给出", "帮我瞅瞅"),
    ("完整用料和关键步骤", "要啥料、步骤咋走"),
    ("完整用料和关键步骤", "用啥料、咋个做"),
    ("家里有", "家里头备着"),
    ("家里有", "手头上有"),
    ("家里有", "冰箱里还剩"),
    ("想做一道家常肉菜", "想整一盘家常荤菜"),
    ("想做一道家常肉菜", "想捣鼓个家常荤菜"),
    ("想做一道蔬菜菜肴", "想整一盘素菜"),
    ("想做一道蔬菜菜肴", "想弄个素菜"),
    ("想做一道海鲜菜", "想弄点海鲜"),
    ("想做一道海鲜菜", "想整点海货"),
    ("想做一道主食", "想捣鼓点饭食"),
    ("想做一道主食", "想弄点吃饱的"),
    ("想做一道早餐", "想整点早饭"),
    ("想做一道早餐", "想弄口早饭"),
    ("想做一道汤品", "想煲点汤汤水水"),
    ("想做一道汤品", "想整锅汤喝"),
    ("应该怎样准备和烹饪", "该咋备料下锅"),
    ("应该怎样准备和烹饪", "要咋个弄熟"),
    ("具体备料和步骤是什么", "咋备料、咋下锅"),
    ("具体备料和步骤是什么", "备啥料、锅里咋走"),
    ("具体步骤是什么", "步骤咋走"),
    ("具体步骤是什么", "咋个走这几步"),
    ("有什么具体做法", "有啥具体作法"),
    ("有什么具体做法", "有啥吃法不"),
    ("步骤怎么安排", "步骤咋排"),
    ("步骤怎么安排", "这几步咋摆"),
    ("步骤怎么做", "这咋整"),
    ("步骤怎么做", "咋个下手"),
    ("做法怎么做", "做法咋弄"),
    ("做法怎么做", "这道咋搞"),
    ("有没有", "有没"),
    ("有没有", "可有"),
    ("需要加入", "得往里搁"),
    ("需要加入", "往里头放点"),
    ("需要控制", "得控着"),
    ("需要控制", "得把温度卡"),
    ("温度控制在", "温度控着在"),
    ("温度控制在", "温度卡在"),
    ("做法怎么安排", "做法咋排"),
    ("做法怎么安排", "咋个安排这做法"),
    ("用量约为", "大概得放"),
    ("用量约为", "大约搁"),
    ("先处理", "先把"),
    ("处理", "弄"),
    ("处理", "拾掇"),
    ("并完成切配", "洗吧切吧"),
    ("再炸至表面上色", "再下锅炸到外头上色"),
    ("再炸至表面上色", "再炸到外皮上色"),
    ("再翻炒至断生", "再扒拉几下炒到断生"),
    ("再翻炒至断生", "再翻两下炒熟"),
    ("再蒸至熟透", "再上锅蒸熟"),
    ("再煮至熟透", "再煮到熟透"),
    ("再烤至表面金黄", "再烤到外头金黄"),
    ("直到熟透入味", "焖到熟烂入味"),
    ("是什么", "是啥"),
)

VAGUE_REPLACEMENTS = (
    ("完整用料和关键步骤", "大概用啥料、步骤大致咋走"),
    ("应该怎样准备和烹饪", "大概该怎么弄熟"),
    ("具体备料和步骤是什么", "大概备啥、顺手咋弄"),
    ("具体步骤是什么", "大概步骤咋走"),
    ("有什么具体做法", "大概有啥吃法"),
    ("步骤怎么安排", "步骤大致咋安排"),
    ("步骤怎么做", "步骤大概咋弄"),
    ("总用时不超过", "总共别耽搁太久，最好不超过"),
    ("需要控制在约", "大概控在"),
    ("约为", "大概是"),
    ("每份约", "每份大概"),
    ("需要加入", "大约得放"),
)

# These maps are applied only to dish names. They deliberately preserve the
# central ingredient/method characters where possible, while making exact
# title matching less reliable for rewrite evaluation.
TITLE_TYPO_MAP = {
    "鸡": "鷄", "鸭": "鴨", "鱼": "魚", "汤": "湯", "饭": "飯",
    "面": "麵", "烧": "焼", "红": "紅", "黄": "黃", "绿": "綠",
    "莲": "蓮", "葱": "蔥", "姜": "薑", "虾": "蝦", "鲤": "鯉",
    "鲈": "鱸", "参": "參", "饼": "餅", "饺": "餃", "馒": "饅",
    "锅": "鍋", "酱": "醬", "煎": "剪", "炸": "砸", "排": "牌",
    "骨": "股", "豆": "荳", "椒": "焦", "肉": "內", "牛": "午",
    "蛋": "旦", "丸": "完", "菜": "采", "包": "苞", "炒": "抄",
    "炖": "燉", "蒸": "烝", "煮": "煑", "焖": "燜", "烤": "考",
    "凉": "涼", "拌": "伴", "炉": "爐", "粉": "份", "鸽": "鴿",
}

TITLE_FUZZY_DROP = (
    "空气炸锅", "微波炉", "老式", "乡村", "脆皮", "现腌", "风味", "甜辣",
    "干煸", "椒盐", "家常", "基础", "手工", "完美", "印度", "日式", "韩式",
    "意式", "苏格兰", "韩国", "河南", "扬州", "阳朔", "红烧", "糖醋", "香煎",
    "清蒸", "葱油", "白灼", "水煮", "凉拌", "微波", "烤", "蒸", "炖", "炒",
)


def _replace_first(text, replacements):
    for old, new in replacements:
        if old in text:
            return text.replace(old, new, 1), True
    return text, False


def _replace_up_to(text, replacements, limit, seed=0):
    grouped = {}
    order = []
    for old, new in replacements:
        if old not in grouped:
            grouped[old] = []
            order.append(old)
        grouped[old].append(new)
    changed = False
    for old in order:
        if old in text:
            variants = grouped[old]
            new = variants[seed % len(variants)]
        else:
            continue
        if old != new:
            text = text.replace(old, new, 1)
            changed = True
            limit -= 1
            if limit <= 0:
                break
    return text, changed


def _title_from_row(row):
    return Path(row["source"]).stem


def _title_typo(title):
    for old, new in TITLE_TYPO_MAP.items():
        if old in title:
            return title.replace(old, new, 1), True
    return title, False


def _title_fuzzy(title):
    core = title
    for token in TITLE_FUZZY_DROP:
        if token in core:
            candidate = core.replace(token, "", 1)
            if len(candidate) >= 2:
                core = candidate
                break
    # When no clear modifier is present, keep the title and make the
    # reference vague through the surrounding wording instead of deleting a
    # potentially meaningful ingredient character.
    return f"那道{core}"


def _replace_title(query, title, replacement):
    if title not in query:
        return query, False
    return query.replace(title, replacement, 1), True


def _food_alias(query, forbidden_terms, seed=0):
    allowed = [pair for pair in FOOD_DIALECT_REPLACEMENTS if pair[0] not in forbidden_terms]
    return _replace_up_to(query, allowed, 1, seed=seed)


def _apply_style(row, style):
    query = row["query"]
    title = _title_from_row(row)
    forbidden = set(row.get("forbidden_terms", []))
    seed = int(row.get("query_id", "0")[:8], 16)

    if style == "typo":
        if row["query_type"] == "dish_name":
            query, title_changed = _replace_title(query, title, _title_typo(title)[0])
        else:
            title_changed = False
        query, text_changed = _replace_up_to(query, TYPO_REPLACEMENTS, 2, seed=seed)
        return query, title_changed or text_changed

    if style == "dialect":
        query, phrase_changed = _replace_up_to(query, DIALECT_REPLACEMENTS, 3, seed=seed)
        query, food_changed = _food_alias(query, forbidden, seed=seed)
        return query, phrase_changed or food_changed

    if style == "vague":
        if row["query_type"] == "dish_name":
            query, title_changed = _replace_title(query, title, _title_fuzzy(title))
        else:
            title_changed = False
        query, phrase_changed = _replace_first(query, VAGUE_REPLACEMENTS)
        return query, title_changed or phrase_changed

    # Mixed: change a title/food token where possible, then use colloquial
    # wording and spelling noise.
    if row["query_type"] == "dish_name":
        query, core_changed = _replace_title(query, title, _title_typo(title)[0])
    else:
        query, core_changed = _food_alias(query, forbidden)
    query, dialect_changed = _replace_up_to(query, DIALECT_REPLACEMENTS, 3, seed=seed)
    query, typo_changed = _replace_up_to(query, TYPO_REPLACEMENTS, 2, seed=seed)
    return query, core_changed or dialect_changed or typo_changed


def _number_fragments(text):
    return re.findall(
        r"\d+(?:\.\d+)?\s*(?:分钟|分|小时|h|℃|°C|摄氏度|度|克|g|公斤|kg|斤|毫升|ml|升|l|大卡|千卡|卡路里)",
        text,
        flags=re.I,
    )


def _validate(original, changed):
    if original.keys() != changed.keys():
        raise ValueError("query record keys changed")
    for key in original:
        if key != "query" and original[key] != changed[key]:
            raise ValueError(f"non-query field changed: {key}")
    if original["query"] == changed["query"]:
        raise ValueError(f"query was not changed: {original.get('query_id')}")
    for term in original.get("forbidden_terms", []):
        if term not in changed["query"]:
            raise ValueError(f"forbidden term lost: {term}")
    if original.get("query_type") == "numeric":
        if _number_fragments(original["query"]) != _number_fragments(changed["query"]):
            raise ValueError(f"numeric fragment changed: {original.get('query_id')}")


def perturb(rows):
    styles = ("typo", "dialect", "vague", "mixed")
    counts = Counter()
    type_counts = Counter()
    output = []
    for original in rows:
        type_index = type_counts[original["query_type"]]
        style = styles[type_index % len(styles)]
        type_counts[original["query_type"]] += 1
        query, changed = _apply_style(original, style)
        if not changed:
            raise ValueError(f"no applicable {style} transformation: {original.get('query_id')}")
        row = dict(original)
        row["query"] = query
        _validate(original, row)
        counts[style] += 1
        output.append(row)
    return output, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("evaluation/datasets/labels/queries.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/datasets/labels/queries_noisy.jsonl"))
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    perturbed, counts = perturb(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in perturbed),
        encoding="utf-8",
    )
    print(f"wrote {len(perturbed)} queries to {args.output}")
    print("styles:", dict(counts))


if __name__ == "__main__":
    main()
