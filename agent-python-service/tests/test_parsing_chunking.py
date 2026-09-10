"""解析器和父子切片器的无外部服务测试。"""

import unittest
from unittest.mock import patch

from familyos_agent.chunking import ParentChildChunker
from familyos_agent.domain import SourceDocument
from familyos_agent.parsing import DocxParser, MarkdownParser, ParserRegistry


# 构造测试用原始文档。
def source(content: str, filename: str = "example.md", extension: str = ".md") -> SourceDocument:
    return SourceDocument(1, 2, 3, 4, filename, extension, "text/markdown", content.encode())


class FakeMetadata:
    """模拟 Unstructured 元素元数据。"""

    # 保存可由 to_dict 输出的元素元数据。
    def __init__(self, **values: object) -> None:
        self._values = values

    # 返回与 Unstructured ElementMetadata 一致的字典接口。
    def to_dict(self) -> dict:
        return dict(self._values)


class FakeElement:
    """模拟 Unstructured 文档元素。"""

    # 构造带类别、ID、正文和树关系的元素。
    def __init__(self, element_id: str, category: str, text: str, **metadata: object) -> None:
        self.id = element_id
        self.category = category
        self.text = text
        self.metadata = FakeMetadata(**metadata)

    # 返回元素正文，兼容 Unstructured 元素字符串行为。
    def __str__(self) -> str:
        return self.text


class FakeSplitter:
    """提供测试用可预测子块切分行为。"""

    # 按固定长度生成子块，用于隔离外部 LangChain 依赖。
    def split_text(self, content: str) -> list[str]:
        return [content[index:index + 40] for index in range(0, len(content), 40)]


class ParsingChunkingTest(unittest.TestCase):
    """验证 Unstructured 元素树和父子映射的核心外部行为。"""

    # Markdown 元素应保留 ID、parent_id、标题路径和表格类型。
    def test_markdown_preserves_unstructured_element_tree(self) -> None:
        elements = [
            FakeElement("title", "Title", "主标题", category_depth=0),
            FakeElement("section", "Title", "子标题", parent_id="title", category_depth=1),
            FakeElement("body", "NarrativeText", "内容", parent_id="section", page_number=1),
            FakeElement("table", "Table", "A | B\n1 | 2", parent_id="section", page_number=1),
        ]
        with patch.object(MarkdownParser, "_partition", return_value=elements):
            parsed = MarkdownParser().parse(source("ignored"))
        self.assertEqual([block.block_type for block in parsed.blocks], ["heading", "heading", "paragraph", "table"])
        self.assertEqual(parsed.blocks[2].heading_path, ("主标题", "子标题"))
        self.assertEqual(parsed.blocks[2].parent_id, "section")
        self.assertEqual(parsed.metadata["parser_version"], "unstructured-elements-v1")

    # Word 解析器应走同一 Unstructured 元素转换逻辑。
    def test_docx_uses_unstructured_elements(self) -> None:
        elements = [FakeElement("title", "Title", "年度计划"), FakeElement("body", "NarrativeText", "计划正文", parent_id="title")]
        document = source("ignored", "plan.docx", ".docx")
        with patch.object(DocxParser, "_partition", return_value=elements):
            parsed = DocxParser().parse(document)
        self.assertEqual(parsed.metadata["source_format"], "word")
        self.assertEqual(parsed.blocks[1].heading_path, ("年度计划",))

    # 共享 parent_id 的元素应形成同一父块，并生成引用该父块的子块。
    def test_parent_child_mapping_groups_by_unstructured_parent_id(self) -> None:
        elements = [
            FakeElement("root", "Title", "知识库"),
            FakeElement("section-a", "Title", "第一章", parent_id="root"),
            FakeElement("a1", "NarrativeText", "甲" * 70, parent_id="section-a"),
            FakeElement("a2", "NarrativeText", "乙" * 30, parent_id="section-a"),
            FakeElement("section-b", "Title", "第二章", parent_id="root"),
            FakeElement("b1", "NarrativeText", "丙" * 20, parent_id="section-b"),
        ]
        with patch.object(MarkdownParser, "_partition", return_value=elements):
            parsed = MarkdownParser().parse(source("ignored"))
        parents, children = ParentChildChunker(40, 5, 1000, splitter=FakeSplitter()).chunk(source("ignored"), parsed)
        parent_ids = {parent.id for parent in parents}
        tree_ids = {parent.metadata["unstructured_parent_id"] for parent in parents}
        self.assertEqual(tree_ids, {"root", "section-a", "section-b"})
        self.assertTrue(all(child.parent_id in parent_ids for child in children))
        self.assertTrue(all(child.metadata["parent_id"] == child.parent_id for child in children))
        self.assertEqual(len({child.id for child in children}), len(children))

    # 没有 parent_id 的普通元素应按父块长度回退聚合。
    def test_top_level_elements_use_size_bounded_fallback_parent(self) -> None:
        elements = [FakeElement("a", "NarrativeText", "甲" * 30), FakeElement("b", "NarrativeText", "乙" * 30)]
        with patch.object(MarkdownParser, "_partition", return_value=elements):
            parsed = MarkdownParser().parse(source("ignored"))
        parents, _ = ParentChildChunker(20, 2, 40, splitter=FakeSplitter()).chunk(source("ignored"), parsed)
        self.assertEqual(len(parents), 2)
        self.assertTrue(all(parent.metadata["unstructured_parent_id"] is None for parent in parents))

    # 注册表应支持 Markdown、Word 和 PDF，并拒绝未知扩展名。
    def test_registry_supports_unstructured_formats(self) -> None:
        registry = ParserRegistry()
        self.assertIsInstance(registry.resolve(".doc", "a.doc"), DocxParser)
        self.assertIsInstance(registry.resolve(".docx", "a.docx"), DocxParser)
        with self.assertRaises(Exception) as context:
            registry.resolve(".xlsx", "a.xlsx")
        self.assertEqual(getattr(context.exception, "code", ""), "UNSUPPORTED_FILE_TYPE")


if __name__ == "__main__":
    unittest.main()
