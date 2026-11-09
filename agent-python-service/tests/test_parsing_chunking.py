"""解析器和父子切片器的无外部服务测试。"""

from pathlib import Path
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
        self.assertEqual(parsed.metadata["parser_version"], "unstructured-document-ocr-v5")

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

    # 真实 Markdown 样本验证识别、结构、表外条件和检索文本的完整链路。
    def test_real_markdown_table(self) -> None:
        content = (Path(__file__).parent / "fixtures/tables/nutrition.md").read_text()
        parsed = MarkdownParser().parse(source(content))
        table = next(block for block in parsed.blocks if block.block_type == "table")
        self.assertEqual(table.metadata["table_structure_status"], "parsed")
        _, children = ParentChildChunker(300, 20, 1000, splitter=FakeSplitter()).chunk(source(content), parsed)
        child = next(child for child in children if child.metadata.get("block_type") == "table")
        self.assertIn("鸡蛋 | 144 | 13.3", child.content)
        self.assertIn("适用于生鲜可食部分", child.content)
        self.assertEqual((child.metadata["row_start"], child.metadata["row_end"]), (2, 3))
        self.assertNotIn("table_rows", child.metadata)

    # 规则表格按行切分时，单位、数据行和引用序号必须完整保留。
    def test_table_rows_preserve_headers_and_provenance(self) -> None:
        html = "<table><caption>每100克</caption><tr><th>食材</th><th>热量（kcal）</th></tr>" + "".join("<tr><td>食材%d</td><td>%d</td></tr>" % (i, i) for i in range(12)) + "</table>"
        elements = [FakeElement("section", "Title", "营养"), FakeElement("table", "Table", "扁平文本", parent_id="section", text_as_html=html, page_number=2)]
        with patch.object(MarkdownParser, "_partition", return_value=elements):
            parsed = MarkdownParser().parse(source("ignored"))
        parents, children = ParentChildChunker(85, 5, 200, splitter=FakeSplitter()).chunk(source("ignored"), parsed)
        tables = [child for child in children if child.metadata.get("block_type") == "table"]
        self.assertGreater(len(tables), 1)
        covered = []
        for child in tables:
            self.assertIn("热量（kcal）", child.content)
            self.assertIn("每100克", child.content)
            self.assertIn("营养", child.content)
            self.assertLessEqual(len(child.content), 85)
            self.assertEqual(child.metadata["page_start"], 2)
            self.assertEqual(child.metadata["table_id"], "table")
            covered.extend(range(child.metadata["row_start"], child.metadata["row_end"] + 1))
        self.assertEqual(covered, list(range(2, 14)))
        parent = next(parent for parent in parents if parent.metadata.get("block_type") == "table")
        self.assertEqual(parent.metadata["text_as_html"], html)
        self.assertTrue(all("扁平文本" not in parent.content for parent in parents if parent.metadata.get("block_type") != "table"))

    # 合并单元格展开后保持列关系，短表只生成一个子块。
    def test_short_table_and_merged_cells(self) -> None:
        html = '<table><tr><th>类别</th><th>数值（g）</th></tr><tr><td rowspan="2">蔬菜</td><td>1</td></tr><tr><td>2</td></tr></table>'
        with patch.object(MarkdownParser, "_partition", return_value=[FakeElement("t", "Table", "原文", text_as_html=html)]):
            parsed = MarkdownParser().parse(source("ignored"))
        self.assertEqual(parsed.blocks[0].metadata["table_rows"], [["类别", "数值（g）"], ["蔬菜", "1"], ["蔬菜", "2"]])
        _, children = ParentChildChunker(100, 5, 200, splitter=FakeSplitter()).chunk(source("ignored"), parsed)
        self.assertEqual(len(children), 1)
        self.assertIn("蔬菜 | 2", children[0].content)

    # 缺失结构不能伪造行号，超长行必须完整保存并明确标记预算例外。
    def test_unavailable_structure_and_oversized_row(self) -> None:
        for html in [None, '<table><tr><td>' + "甲" * 150 + '</td></tr></table>']:
            with patch.object(DocxParser, "_partition", return_value=[FakeElement("t", "Table", "甲" * 150, text_as_html=html)]):
                parsed = DocxParser().parse(source("ignored"))
            _, children = ParentChildChunker(40, 5, 200, splitter=FakeSplitter()).chunk(source("ignored"), parsed)
            self.assertEqual(len(children), 1)
            self.assertEqual(children[0].content, "甲" * 150)
            self.assertTrue(children[0].metadata["table_budget_exceeded"])
            self.assertEqual(children[0].metadata["row_start"], 1 if html else None)

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
