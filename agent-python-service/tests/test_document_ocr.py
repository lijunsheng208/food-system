"""验证 DOCX 图片 OCR 的位置、结构、缓存及来源贯通，不下载模型。"""

import io
import os
import unittest
from unittest.mock import patch

from docx import Document
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from PIL import Image, ImageDraw
from unstructured.documents.elements import ElementMetadata, NarrativeText, Table, Title

from familyos_agent.chunking import ParentChildChunker
from familyos_agent.document_ocr import OCR_AGENT, _recognize_image, _validate_image
from familyos_agent.domain import PermanentDocumentError, SourceDocument
from familyos_agent.parsing import DocxParser, PdfParser


# 生成带可识别文字的真实 PNG，作为 Word 内嵌图片及扫描 PDF 的源资源。
def image_bytes() -> bytes:
    image = Image.new("RGB", (800, 160), "white")
    ImageDraw.Draw(image).text((20, 40), "Egg energy 144 kcal", fill="black", font_size=40)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


# 生成包含正文、图片及表格内图片的 DOCX 字节。
def word_with_images(repeat: bool = False, in_table: bool = False, external: bool = False) -> SourceDocument:
    document = Document()
    document.add_heading("营养信息", 1)
    document.add_paragraph("图片前的正文。")
    paragraph = document.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0] if in_table else document.add_paragraph()
    paragraph.add_run("每100克食材。")
    paragraph.add_run().add_picture(io.BytesIO(image_bytes()))
    if repeat:
        document.add_paragraph().add_run().add_picture(io.BytesIO(image_bytes()))
    if external:
        blip = document.element.body.xpath(".//a:blip")[0]
        rid = document.part.relate_to("https://example.invalid/image.png", RELATIONSHIP_TYPE.IMAGE, is_external=True)
        blip.set(qn("r:embed"), rid)
    document.add_paragraph("图片后的正文。")
    output = io.BytesIO()
    document.save(output)
    return SourceDocument(1, 2, 3, 4, "images.docx", ".docx", "", output.getvalue())


class DocumentOcrTest(unittest.TestCase):
    """验证图片 OCR 适配与已有分块的业务行为。"""

    # 相同图片仅识别一次，每次出现仍保留独立来源和正常的文档顺序。
    def test_word_image_order_heading_and_cache(self) -> None:
        result = [Title("鸡蛋热量144 kcal", metadata=ElementMetadata(page_number=1))]
        with patch("familyos_agent.document_ocr._recognize_image", return_value=result) as recognize:
            source = word_with_images(repeat=True)
            parsed = DocxParser().parse(source)
        self.assertEqual(recognize.call_count, 1)
        images = [block for block in parsed.blocks if block.metadata.get("ocr_source_type") == "docx_image"]
        self.assertEqual(len(images), 2)
        self.assertNotEqual(images[0].element_id, images[1].element_id)
        self.assertEqual(images[0].heading_path, ("营养信息",))
        self.assertEqual(images[0].block_type, "paragraph")
        self.assertIsNone(images[0].page_number)
        self.assertIn("drawing", images[0].metadata["image_source_xpath"])
        texts = [block.text for block in parsed.blocks]
        self.assertLess(texts.index("图片前的正文。"), texts.index("鸡蛋热量144 kcal"))
        self.assertLess(texts.index("鸡蛋热量144 kcal"), texts.index("图片后的正文。"))
        self.assertFalse(any("FamilyOS OCR image placeholder" in text for text in texts))
        _, children = ParentChildChunker(200, 10, 500).chunk(source, parsed)
        child = next(chunk for chunk in children if chunk.metadata.get("image_id") == images[0].metadata["image_id"])
        self.assertEqual(child.metadata["image_sha256"], images[0].metadata["image_sha256"])
        self.assertEqual(child.metadata["heading_path"], ["营养信息"])
        self.assertEqual(child.metadata["source_elements"][0]["image_source_xpath"], images[0].metadata["image_source_xpath"])

    # 原生表格内图片的识别结果可复用表格分块，且不会干扰原生表格数量关联。
    def test_image_table_inside_native_word_table(self) -> None:
        html = "<table><tr><th>食材</th><th>热量（kcal）</th></tr><tr><td>鸡蛋</td><td>144</td></tr></table>"
        result = [Table("食材 热量（kcal） 鸡蛋 144", metadata=ElementMetadata(text_as_html=html))]
        with patch("familyos_agent.document_ocr._recognize_image", return_value=result):
            source = word_with_images(in_table=True)
            parsed = DocxParser().parse(source)
        image = next(block for block in parsed.blocks if block.metadata.get("image_id"))
        self.assertEqual(image.metadata["table_rows"][1], ["鸡蛋", "144"])
        self.assertIn("/w:tc/", image.metadata["image_source_xpath"])
        parents, children = ParentChildChunker(200, 10, 500).chunk(source, parsed)
        child = next(chunk for chunk in children if chunk.metadata.get("image_id"))
        self.assertIn("鸡蛋 | 144", child.content)
        self.assertEqual(child.metadata["row_start"], 2)
        parent = next(chunk for chunk in parents if chunk.id == child.parent_id)
        self.assertEqual(parent.metadata["text_as_html"], html)

    # 装饰图片无文字可以忽略，但必须记录 no_text，不能声称图片已识别出文本。
    def test_empty_image_text_is_recorded(self) -> None:
        with patch("familyos_agent.document_ocr._recognize_image", return_value=[]):
            parsed = DocxParser().parse(word_with_images())
        self.assertEqual(parsed.metadata["image_ocr_results"][0]["status"], "no_text")
        self.assertTrue(any("图片后的正文" in block.text for block in parsed.blocks))

    # 外链不得触发网络下载，OCR 引擎故障也不得被吞掉后返回成功。
    def test_external_images_and_engine_failure(self) -> None:
        with patch("familyos_agent.document_ocr._recognize_image") as recognize:
            with self.assertRaises(PermanentDocumentError) as context:
                DocxParser().parse(word_with_images(external=True))
            recognize.assert_not_called()
        self.assertEqual(context.exception.code, "DOCUMENT_IMAGE_EXTERNAL")
        with patch("familyos_agent.document_ocr._recognize_image", side_effect=RuntimeError("engine unavailable")):
            with self.assertRaises(PermanentDocumentError) as context:
                DocxParser().parse(word_with_images())
        self.assertEqual(context.exception.code, "DOCUMENT_PARSE_FAILED")

    # 损坏资源和超出像素预算的图片不能进入 OCR 模型。
    def test_invalid_and_oversized_image(self) -> None:
        with self.assertRaises(PermanentDocumentError) as context:
            _validate_image(b"not an image")
        self.assertEqual(context.exception.code, "DOCUMENT_IMAGE_INVALID")
        with patch("PIL.Image.open") as open_image:
            image = open_image.return_value.__enter__.return_value
            image.format = "PNG"
            image.width = image.height = 10000
            with self.assertRaises(PermanentDocumentError) as context:
                _validate_image(b"image")
        self.assertEqual(context.exception.code, "DOCUMENT_IMAGE_TOO_LARGE")

    # 图片解析与 PDF 均显式使用中英文 OCR 和表格结构推断。
    def test_image_ocr_parameters(self) -> None:
        with patch("unstructured.partition.image.partition_image", return_value=[]) as partition:
            _recognize_image(image_bytes())
        kwargs = partition.call_args.kwargs
        self.assertEqual(kwargs["strategy"], "hi_res")
        self.assertTrue(kwargs["infer_table_structure"])
        self.assertEqual(kwargs["languages"], ["chi_sim", "eng"])
        self.assertEqual(kwargs["ocr_agent"], OCR_AGENT)
        self.assertEqual(kwargs["table_ocr_agent"], OCR_AGENT)

    # 真正的图片与扫描页 OCR 只在预装系统依赖及模型的验收环境运行。
    @unittest.skipUnless(os.environ.get("FAMILYOS_TEST_PDF_HI_RES") == "1", "需预装 OCR 系统依赖及模型")
    def test_real_word_image_and_scanned_pdf(self) -> None:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen.canvas import Canvas

        parsed_word = DocxParser().parse(word_with_images())
        word_text = " ".join(block.text for block in parsed_word.blocks if block.metadata.get("image_id"))
        self.assertIn("144", word_text)
        output = io.BytesIO()
        canvas = Canvas(output)
        canvas.drawImage(ImageReader(io.BytesIO(image_bytes())), 40, 400, width=500, height=100)
        canvas.save()
        source = SourceDocument(1, 2, 3, 4, "scan.pdf", ".pdf", "", output.getvalue())
        parsed_pdf = PdfParser().parse(source)
        self.assertIn("144", " ".join(block.text for block in parsed_pdf.blocks))
        self.assertTrue(all(block.page_number == 1 for block in parsed_pdf.blocks))


if __name__ == "__main__":
    unittest.main()
