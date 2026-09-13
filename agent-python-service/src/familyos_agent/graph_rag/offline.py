"""阶段 1 离线建图验证：从 HowToCook Markdown 生成可审计的图候选。"""

import hashlib
import re
from pathlib import Path
from typing import Iterable, List, Tuple

from ..domain import ChildChunk, DocumentBlock, ParsedDocument
from .models import GraphEntity, GraphRelation


_INGREDIENT_HEADING = re.compile(r"^#+\s*(必备原料和工具|原料|食材|配料)")
_OPERATION_HEADING = re.compile(r"^#+\s*(操作|步骤|做法)")
_LIST_ITEM = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_NUMBERED_STEP = re.compile(r"^\s*(\d+)[.、)]\s*(.+?)\s*$")


def _clean_ingredient(value: str) -> str:
    """清理食材列表项中的可选说明，保留可用于实体规范化的名称。"""
    return re.sub(r"\s*[（(].*?[）)]", "", value).strip()


def parse_recipe_markdown(path: Path) -> Tuple[str, List[str], List[str]]:
    """从 HowToCook 菜谱 Markdown 提取菜名、食材和有序步骤。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    title = next((m.group(1).strip() for line in lines if (m := re.match(r"^#\s+(.+)$", line))), path.stem)
    ingredients: List[str] = []
    steps: List[str] = []
    section = ""
    for line in lines:
        if _INGREDIENT_HEADING.match(line):
            section = "ingredients"
            continue
        if _OPERATION_HEADING.match(line):
            section = "steps"
            continue
        if line.startswith("## "):
            section = ""
        if section == "ingredients":
            match = _LIST_ITEM.match(line)
            if match and (value := _clean_ingredient(match.group(1))):
                ingredients.append(value)
        elif section == "steps":
            match = _NUMBERED_STEP.match(line)
            if match:
                steps.append(match.group(2).strip())
    return title, list(dict.fromkeys(ingredients)), steps


def build_recipe_graph_candidates(path: Path, user_id: int = 0, knowledge_base_id: int = 0, index_version: int = 1) -> Tuple[List[GraphEntity], List[GraphRelation]]:
    """为单个菜谱生成确定性实体关系候选，并保留文件来源。"""
    title, ingredients, steps = parse_recipe_markdown(path)
    # 使用稳定摘要生成离线文档标识，避免 Python hash 随进程随机化导致重复建图。
    document_key = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    document_id = int(document_key, 16)
    recipe_id = "recipe:%d" % document_id
    recipe_chunk_id = "offline:%s:recipe" % document_key
    entities: List[GraphEntity] = [GraphEntity(recipe_id, "Recipe", title, user_id, knowledge_base_id, document_id, index_version, recipe_chunk_id, aliases=[])]
    relations: List[GraphRelation] = []
    for index, ingredient in enumerate(ingredients):
        entity_id = "ingredient:%d:%d" % (document_id, index)
        entities.append(GraphEntity(entity_id, "Ingredient", ingredient, user_id, knowledge_base_id, document_id, index_version, recipe_chunk_id))
        relations.append(GraphRelation("requires:%d:%d" % (document_id, index), "REQUIRES", recipe_id, entity_id, user_id, knowledge_base_id, document_id, index_version, recipe_chunk_id))
    step_ids: List[str] = []
    for index, step in enumerate(steps, 1):
        entity_id = "step:%d:%d" % (document_id, index)
        step_ids.append(entity_id)
        step_chunk_id = "offline:%s:step:%d" % (document_key, index)
        entities.append(GraphEntity(entity_id, "CookingStep", step, user_id, knowledge_base_id, document_id, index_version, step_chunk_id))
        relations.append(GraphRelation("contains-step:%d:%d" % (document_id, index), "CONTAINS_STEP", recipe_id, entity_id, user_id, knowledge_base_id, document_id, index_version, step_chunk_id))
        if index > 1:
            relations.append(GraphRelation("precedes:%d:%d" % (document_id, index), "PRECEDES", step_ids[-2], entity_id, user_id, knowledge_base_id, document_id, index_version, step_chunk_id))
    return entities, relations


def discover_markdown_files(root: Path, limit: int = 0) -> Iterable[Path]:
    """按稳定路径顺序发现菜谱 Markdown 文件。"""
    paths = sorted(root.rglob("*.md"))
    return paths[:limit] if limit > 0 else paths
