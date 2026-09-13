"""从文档块抽取图实体和关系的 LLM 适配器。"""

import json
from typing import Any, Mapping, Sequence, Tuple, Union

from ..domain import ChildChunk, ParentChunk
from .models import GraphEntity, GraphRelation, ALLOWED_RELATION_TYPES


class LLMGraphExtractor:
    """调用兼容 OpenAI Chat API 的模型生成受限图谱候选。"""

    def __init__(self, model: Any, confidence_threshold: float = 0.7) -> None:
        if model is None or not 0 <= confidence_threshold <= 1:
            raise ValueError("图抽取器配置无效")
        self._model = model
        self._threshold = confidence_threshold

    # 从单个 chunk 抽取实体和关系，并严格绑定来源 chunk。
    def extract(self, chunk: Union[ChildChunk, ParentChunk]) -> Tuple[list[GraphEntity], list[GraphRelation]]:
        prompt = [
            {"role": "system", "content": "你是知识图谱抽取器。只抽取原文明确表达的菜谱实体和关系，不补充常识。实体类型只能是 Recipe、Ingredient、CookingStep、Cuisine、DietTag、Tool；关系只能是 REQUIRES、CONTAINS_STEP、BELONGS_TO_CATEGORY、SUITABLE_FOR、PAIRS_WITH、PRECEDES。只输出 JSON：{\"entities\":[{\"name\":\"\",\"type\":\"\",\"confidence\":0.0}],\"relations\":[{\"source\":\"\",\"type\":\"\",\"target\":\"\",\"confidence\":0.0}]}"},
            {"role": "user", "content": chunk.content},
        ]
        if not hasattr(self._model, "invoke"):
            raise TypeError("图抽取模型必须提供同步 invoke 接口")
        response = self._model.invoke(prompt)
        content = response.get("content", "") if isinstance(response, Mapping) else getattr(response, "content", "")
        raw_content = str(content).strip()
        if raw_content.startswith("```"):
            raw_content = raw_content.split("\n", 1)[1] if "\n" in raw_content else raw_content
            raw_content = raw_content.rsplit("```", 1)[0].strip()
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            # 兼容模型在 JSON 前后附带说明文字，优先截取首个完整对象。
            start, end = raw_content.find("{"), raw_content.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("LLM 图抽取返回格式无效")
            payload = json.loads(raw_content[start : end + 1])
        raw_entities = payload.get("entities", [])
        entity_map: dict[tuple[str, str], GraphEntity] = {}
        for item in raw_entities:
            name, entity_type = str(item.get("name", "")).strip(), str(item.get("type", "")).strip()
            confidence = float(item.get("confidence", 0))
            if name and entity_type in {"Recipe", "Ingredient", "CookingStep", "Cuisine", "DietTag", "Tool"} and confidence >= self._threshold:
                entity_id = "%s:%s:%s" % (entity_type.lower(), chunk.id, name)
                entity_map[(name, entity_type)] = GraphEntity(entity_id, entity_type, name, chunk.user_id, chunk.knowledge_base_id, chunk.document_id, chunk.index_version, chunk.id, confidence=confidence)
        relations: list[GraphRelation] = []
        for index, item in enumerate(payload.get("relations", [])):
            source, relation_type, target = str(item.get("source", "")).strip(), str(item.get("type", "")).strip(), str(item.get("target", "")).strip()
            confidence = float(item.get("confidence", 0))
            if relation_type not in ALLOWED_RELATION_TYPES or confidence < self._threshold:
                continue
            source_entity = next((entity for (name, _), entity in entity_map.items() if name == source), None)
            target_entity = next((entity for (name, _), entity in entity_map.items() if name == target), None)
            if source_entity and target_entity:
                relations.append(GraphRelation("%s:%s:%d" % (relation_type.lower(), chunk.id, index), relation_type, source_entity.entity_id, target_entity.entity_id, chunk.user_id, chunk.knowledge_base_id, chunk.document_id, chunk.index_version, chunk.id, confidence=confidence))
        return list(entity_map.values()), relations
