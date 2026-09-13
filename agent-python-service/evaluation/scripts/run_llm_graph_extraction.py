"""阶段 1 LLM 离线建图验证：基于父块抽取 HowToCook 菜谱实体关系。"""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import yaml

SERVICE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from familyos_agent.chunking import ParentChildChunker
from familyos_agent.domain import ParentChunk, SourceDocument
from familyos_agent.graph_rag import LLMGraphExtractor
from familyos_agent.parsing import MarkdownParser


class SyncOpenAIModel:
    """调用 OpenAI-compatible Chat Completions 接口，供离线抽取使用。"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float, max_tokens: int = 1200) -> None:
        if not base_url or not api_key or not model or timeout <= 0:
            raise ValueError("LLM 抽取配置不完整")
        if max_tokens <= 0:
            raise ValueError("max_tokens 必须为正数")
        self.base_url, self.api_key, self.model, self.timeout, self.max_tokens = base_url, api_key, model, timeout, max_tokens

    # 同步调用一次结构化抽取请求，适配离线脚本逐块处理。
    def invoke(self, messages: list[dict[str, str]]) -> dict[str, str]:
        response = httpx.post(self.base_url.rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + self.api_key}, json={"model": self.model, "messages": messages, "temperature": 0, "max_tokens": self.max_tokens, "response_format": {"type": "json_object"}}, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        return {"content": str(body["choices"][0]["message"].get("content", ""))}


def _duration(value: Any) -> float:
    """解析配置中的秒数或带单位持续时间。"""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    factors = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    for suffix, factor in factors.items():
        if text.endswith(suffix):
            return float(text[: -len(suffix)].strip()) * factor
    return float(text)


def _extraction_units(path: Path, child_size: int, child_overlap: int, parent_size: int, max_document_chars: int):
    """按文档长度和标题数量选择整篇或 FamilyOS 父块作为抽取单位。"""
    content = path.read_bytes()
    document_id = int(hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16], 16)
    source = SourceDocument(document_id, 0, 0, 1, path.name, ".md", "text/markdown", content)
    parsed = MarkdownParser().parse(source)
    # 只把一级标题视为文档/菜谱标题，二级章节标题属于同一主题上下文。
    headings = sum(block.block_type == "heading" and (block.heading_level or 1) == 1 for block in parsed.blocks)
    full_content = "\n\n".join(block.text for block in parsed.blocks if block.text.strip())
    if headings <= 1 and len(full_content) <= max_document_chars:
        # 单菜谱短文档整篇抽取，保证标题、食材和步骤在同一上下文中。
        digest = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
        return [ParentChunk("graph-document:%s" % source.document_id, source.document_id, source.knowledge_base_id, source.user_id, source.index_version, 0, full_content, digest, {"extraction_scope": "document", "heading_count": headings})]
    # 长文档或多主题文档按 FamilyOS 父块抽取，降低上下文和单次输出风险。
    parents = ParentChildChunker(child_size, child_overlap, parent_size).chunk(source, parsed)[0]
    return [ParentChunk(parent.id, parent.document_id, parent.knowledge_base_id, parent.user_id, parent.index_version, parent.index, parent.content, parent.content_sha256, {**parent.metadata, "extraction_scope": "parent", "heading_count": headings}) for parent in parents]


def main() -> None:
    """批量以父块为上下文调用 LLM，输出 JSONL 和质量统计。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="../../HowToCook-master/dishes")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--output", default="evaluation/experiments/graph-stage1/llm_candidates.jsonl")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--confidence-threshold", type=float, default=None)
    parser.add_argument("--child-size", type=int, default=500)
    parser.add_argument("--child-overlap", type=int, default=50)
    parser.add_argument("--parent-size", type=int, default=4000)
    parser.add_argument("--max-document-chars", type=int, default=12000)
    parser.add_argument("--max-tokens", type=int, default=None)
    args = parser.parse_args()
    config_data = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) if Path(args.config).exists() else {}
    configured = config_data.get("graph_extraction", {}) if isinstance(config_data, dict) else {}
    base_url = args.base_url or os.getenv("FAMILYOS_AGENT_GRAPH_EXTRACTION_BASE_URL", configured.get("base_url", ""))
    api_key = args.api_key or os.getenv("FAMILYOS_AGENT_GRAPH_EXTRACTION_API_KEY", configured.get("api_key", ""))
    model_name = args.model or os.getenv("FAMILYOS_AGENT_GRAPH_EXTRACTION_MODEL", configured.get("model", ""))
    timeout = args.timeout if args.timeout is not None else _duration(configured.get("timeout", 30.0))
    max_tokens = args.max_tokens if args.max_tokens is not None else int(configured.get("max_tokens", 1200))
    confidence_threshold = args.confidence_threshold if args.confidence_threshold is not None else float(configured.get("confidence_threshold", 0.7))
    if args.limit < 0 or args.max_document_chars <= 0 or not 0 <= confidence_threshold <= 1:
        raise ValueError("limit 或 confidence-threshold 无效")
    model = SyncOpenAIModel(base_url, api_key, model_name, timeout, max_tokens)
    extractor = LLMGraphExtractor(model, confidence_threshold)
    paths = sorted(Path(args.input).resolve().rglob("*.md"))[:args.limit or None]
    if not paths:
        raise ValueError("未找到 Markdown 菜谱")
    rows, counts = [], Counter()
    for path in paths:
        entities, relations = [], []
        chunks = _extraction_units(path, args.child_size, args.child_overlap, args.parent_size, args.max_document_chars)
        for chunk in chunks:
            found_entities, found_relations = extractor.extract(chunk)
            entities.extend(found_entities)
            relations.extend(found_relations)
        counts.update(entity.entity_type for entity in entities)
        counts.update(relation.relation_type for relation in relations)
        rows.append({"source_file": str(path), "extraction_scope": chunks[0].metadata.get("extraction_scope", "unknown") if chunks else "unknown", "extraction_unit_count": len(chunks), "entities": [item.__dict__ for item in entities], "relations": [item.__dict__ for item in relations]})
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(rows), "entity_counts": {key: counts[key] for key in ("Recipe", "Ingredient", "CookingStep", "Tool", "Cuisine", "DietTag")}, "relation_counts": {key: counts[key] for key in ("REQUIRES", "CONTAINS_STEP", "BELONGS_TO_CATEGORY", "SUITABLE_FOR", "PAIRS_WITH", "PRECEDES")}, "output": str(output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
