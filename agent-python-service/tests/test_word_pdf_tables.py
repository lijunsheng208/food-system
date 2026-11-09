"""通过真实内存 Word/PDF 文件验证表格识别到行分块的链路。"""

import io
import unittest

from docx import Document
from docx.oxml import OxmlElement
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, PageBreak
from reportlab.lib.styles import getSampleStyleSheet

from familyos_agent.chunking import ParentChildChunker
from familyos_agent.domain import SourceDocument, PermanentDocumentError
from familyos_agent.parsing import DocxParser, PdfParser


# 以真实文件字节构造无外部服务的索引来源。
def document_source(content: bytes, suffix: str) -> SourceDocument:
    return SourceDocument(11, 12, 13, 14, "nutrition" + suffix, suffix, "", content)


# 生成含真实表头标记和纵向合并单元格的 Word 测试文件。
def word_sample() -> bytes:
    document = Document()
    document.add_heading("Nutrition", 1)
    document.add_paragraph("Per 100g edible portion.")
    table = document.add_table(rows=1, cols=3)
    for cell, text in zip(table.rows[0].cells, ["Category", "Food", "Energy(kcal)"]):
        cell.text = text
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for index in range(16):
        for cell, text in zip(table.add_row().cells, ["Vegetable", "Food%d" % index, str(100 + index)]):
            cell.text = text
    table.cell(1, 0).merge(table.cell(2, 0)).text = "Vegetable"
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


# 生成两页带网格的文字 PDF，含合并单元格及表外正文。
def pdf_sample() -> bytes:
    output = io.BytesIO()
    story = []
    for page in range(2):
        story.append(Paragraph("Per 100g edible portion.", getSampleStyleSheet()["Normal"]))
        rows = [["Category", "Food", "Energy(kcal)"]] + [["Vegetable", "P%dFood%d" % (page, i), str(100 + i)] for i in range(12)]
        table = Table(rows, colWidths=[100, 100, 100])
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black), ("SPAN", (0, 1), (0, 2))]))
        story.append(table)
        story.append(Paragraph("After table paragraph.", getSampleStyleSheet()["Normal"]))
        if page == 0:
            story.append(PageBreak())
    SimpleDocTemplate(output).build(story)
    return output.getvalue()


class WordPdfTableTest(unittest.TestCase):
    """验证可识别 Word 和有线 PDF，不依赖 OCR、视觉模型或网络。"""

    # Word 标题行和合并值在按行分块后仍可与数值对应。
    def test_word_headers_merged_cells_and_rows(self) -> None:
        source = document_source(word_sample(), ".docx")
        parsed = DocxParser().parse(source)
        table = next(block for block in parsed.blocks if block.block_type == "table")
        self.assertEqual(table.metadata["table_header_row_count"], 1)
        self.assertEqual(table.metadata["table_rows"][2], ["Vegetable", "Food1", "101"])
        self.assertIn("vMerge", table.metadata["table_source_xml"])
        parents, children = ParentChildChunker(200, 10, 1000).chunk(source, parsed)
        chunks = [child for child in children if child.metadata.get("block_type") == "table"]
        covered = []
        for chunk in chunks:
            self.assertIn("Energy(kcal)", chunk.content)
            self.assertIn("Per 100g", chunk.content)
            self.assertLessEqual(len(chunk.content), 200)
            covered.extend(range(chunk.metadata["row_start"], chunk.metadata["row_end"] + 1))
            self.assertNotIn("table_source_xml", chunk.metadata)
        self.assertEqual(covered, list(range(2, 18)))
        self.assertEqual(sum(parent.metadata.get("block_type") == "table" for parent in parents), 1)

    # PDF 的页码、实际坐标和网格应保留，正文不得再次包含表格数据。
    def test_pdf_tables_pages_and_no_duplicate_body(self) -> None:
        source = document_source(pdf_sample(), ".pdf")
        parsed = PdfParser().parse(source)
        tables = [block for block in parsed.blocks if block.block_type == "table"]
        self.assertEqual(len(tables), 2)
        self.assertEqual([table.page_number for table in tables], [1, 2])
        self.assertEqual(tables[0].metadata["table_rows"][2], ["Vegetable", "P0Food1", "101"])
        self.assertEqual(len(tables[0].metadata["table_bbox"]), 4)
        body = "\n".join(block.text for block in parsed.blocks if block.block_type != "table")
        self.assertNotIn("P0Food", body)
        self.assertIn("After table paragraph", body)
        _, children = ParentChildChunker(230, 10, 1000).chunk(source, parsed)
        for table in tables:
            chunks = [child for child in children if child.metadata.get("table_id") == table.element_id]
            self.assertTrue(chunks)
            covered = []
            for chunk in chunks:
                self.assertIn("Energy(kcal)", chunk.content)
                self.assertIn("Per 100g", chunk.content)
                self.assertEqual(chunk.metadata["page_start"], table.page_number)
                self.assertLessEqual(len(chunk.content), 230)
                covered.extend(range(chunk.metadata["row_start"], chunk.metadata["row_end"] + 1))
            self.assertEqual(covered, list(range(1, 14)))

    # 未设置 Word 重复表头标记时不得擅自消耗首行数据。
    def test_word_without_header_marker(self) -> None:
        document = Document()
        table = document.add_table(rows=2, cols=2)
        for row, values in zip(table.rows, [["Egg", "144"], ["Tomato", "15"]]):
            for cell, value in zip(row.cells, values):
                cell.text = value
        output = io.BytesIO()
        document.save(output)
        source = document_source(output.getvalue(), ".docx")
        parsed = DocxParser().parse(source)
        block = next(block for block in parsed.blocks if block.block_type == "table")
        self.assertEqual(block.metadata["table_header_row_count"], 0)
        _, chunks = ParentChildChunker(100, 10, 200).chunk(source, parsed)
        self.assertEqual(chunks[0].metadata["row_start"], 1)
        self.assertIn("Egg | 144", chunks[0].content)

    # 普通 PDF 保留正文；损坏文件必须返回解析失败，而非空成功结果。
    def test_pdf_plain_text_and_corruption(self) -> None:
        from reportlab.pdfgen.canvas import Canvas

        output = io.BytesIO()
        canvas = Canvas(output)
        canvas.drawString(72, 720, "Plain document body.")
        canvas.save()
        parsed = PdfParser().parse(document_source(output.getvalue(), ".pdf"))
        self.assertIn("Plain document body.", parsed.blocks[0].text)
        self.assertFalse(any(block.block_type == "table" for block in parsed.blocks))
        with self.assertRaises(PermanentDocumentError) as context:
            PdfParser().parse(document_source(b"broken PDF", ".pdf"))
        self.assertEqual(context.exception.code, "DOCUMENT_PARSE_FAILED")

    # 空白 PDF 不得伪装为成功的表格解析结果。
    def test_blank_pdf_reports_missing_text(self) -> None:
        from reportlab.pdfgen.canvas import Canvas

        output = io.BytesIO()
        canvas = Canvas(output)
        canvas.showPage()
        canvas.save()
        with self.assertRaises(PermanentDocumentError) as context:
            PdfParser().parse(document_source(output.getvalue(), ".pdf"))
        self.assertEqual(context.exception.code, "PDF_TEXT_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
