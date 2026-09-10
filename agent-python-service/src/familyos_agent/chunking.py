"""根据 Unstructured 元素树生成父块和可检索子块。"""

import hashlib
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .domain import ChildChunk, DocumentBlock, ParentChunk, ParsedDocument, SourceDocument


_CHUNK_NAMESPACE = uuid.UUID("d998d28b-a9d6-45df-b37f-ebcd379c33f4")


# 计算文本摘要，用于幂等校验和索引内容追踪。
def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# 将结构块渲染为适合检索和生成的规范化文本。
def _render_block(block: DocumentBlock) -> str:
    if block.block_type == "heading":
        return "%s %s" % ("#" * (block.heading_level or 1), block.text)
    if block.block_type == "list_item":
        return "- " + block.text
    return block.text


class ParentChildChunker:
    """先按元素 parent_id 聚合父块，再用 LangChain 递归切分子块。"""

    # 校验父子块长度，防止生成不可检索或无法进入模型的切片。
    def __init__(self, child_size: int, child_overlap: int, parent_size: int, splitter: Optional[Any] = None) -> None:
        if child_size <= 0 or child_overlap < 0 or child_overlap >= child_size or parent_size < child_size:
            raise ValueError("父子切片配置无效")
        self.child_size = child_size
        self.child_overlap = child_overlap
        self.parent_size = parent_size
        self._splitter = splitter or self._create_splitter()

    # 创建适合中英文文档的 LangChain 递归字符切分器。
    def _create_splitter(self) -> Any:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError as exc:
            raise RuntimeError("缺少 langchain-text-splitters，请重新安装 agent-python-service") from exc
        return RecursiveCharacterTextSplitter(
            chunk_size=self.child_size,
            chunk_overlap=self.child_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", ". ", "! ", "? ", "; ", "，", ", ", " ", ""],
        )

    # 生成父块及其子块，子块 parent_id 始终指向同版本父块。
    def chunk(self, source: SourceDocument, parsed: ParsedDocument) -> Tuple[List[ParentChunk], List[ChildChunk]]:
        groups = self._group_parent_blocks(parsed.blocks)
        parents: List[ParentChunk] = []
        children: List[ChildChunk] = []
        for parent_index, (tree_parent_id, blocks) in enumerate(groups):
            content = "\n\n".join(_render_block(block) for block in blocks if block.text.strip()).strip()
            if not content:
                continue
            parent_id = str(uuid.uuid5(_CHUNK_NAMESPACE, "%d:%d:parent:%s:%s" % (source.document_id, source.index_version, tree_parent_id, _digest(content))))
            pages = [block.page_number for block in blocks if block.page_number is not None]
            heading_path = next((block.heading_path for block in blocks if block.heading_path), ())
            parent_metadata: Dict[str, object] = {
                "filename": source.filename,
                "content_type": source.content_type,
                "source_format": parsed.metadata.get("source_format", ""),
                "parser_version": parsed.metadata.get("parser_version", ""),
                "heading_path": list(heading_path),
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "unstructured_parent_id": tree_parent_id if not tree_parent_id.startswith("fallback:") else None,
                "element_ids": [block.element_id for block in blocks if block.element_id],
            }
            parent = ParentChunk(parent_id, source.document_id, source.knowledge_base_id, source.user_id, source.index_version, parent_index, content, _digest(content), parent_metadata)
            parents.append(parent)
            for local_index, child_text in enumerate(self._split_child_text(content)):
                child_index = len(children)
                child_id = str(uuid.uuid5(_CHUNK_NAMESPACE, "%d:%d:child:%d:%s" % (source.document_id, source.index_version, child_index, _digest(child_text))))
                child_metadata = dict(parent_metadata)
                child_metadata.update({"parent_id": parent_id, "parent_index": parent_index, "child_index_in_parent": local_index})
                children.append(ChildChunk(child_id, parent_id, source.document_id, source.knowledge_base_id, source.user_id, source.index_version, child_index, child_text, _digest(child_text), child_metadata))
        return parents, children

    # 按直接 parent_id 聚合元素；没有树关系的顶层元素按长度回退聚合。
    def _group_parent_blocks(self, blocks: Sequence[DocumentBlock]) -> List[Tuple[str, List[DocumentBlock]]]:
        by_id = {block.element_id: block for block in blocks if block.element_id}
        referenced_ids = {block.parent_id for block in blocks if block.parent_id}
        grouped: Dict[str, List[DocumentBlock]] = {}
        order: List[str] = []
        for block in blocks:
            if not block.parent_id:
                continue
            if block.parent_id not in grouped:
                order.append(block.parent_id)
                grouped[block.parent_id] = []
            grouped[block.parent_id].append(block)

        result: List[Tuple[str, List[DocumentBlock]]] = []
        for parent_id in order:
            members = grouped[parent_id]
            parent = by_id.get(parent_id)
            result.append((parent_id, ([parent] if parent is not None else []) + members))

        fallback: List[DocumentBlock] = []
        fallback_size = 0
        fallback_index = 0
        for block in blocks:
            if block.parent_id or block.element_id in referenced_ids:
                continue
            rendered_size = len(_render_block(block)) + 2
            if fallback and fallback_size + rendered_size > self.parent_size:
                result.append(("fallback:%d" % fallback_index, fallback))
                fallback_index += 1
                fallback = []
                fallback_size = 0
            fallback.append(block)
            fallback_size += rendered_size
        if fallback:
            result.append(("fallback:%d" % fallback_index, fallback))
        return sorted(result, key=lambda item: min(block.order for block in item[1]))

    # 调用 LangChain 递归字符切分器生成带配置重叠的子块。
    def _split_child_text(self, content: str) -> List[str]:
        return [value.strip() for value in self._splitter.split_text(content) if value.strip()]
