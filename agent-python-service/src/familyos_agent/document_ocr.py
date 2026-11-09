"""提取 DOCX 正文内图片，使用 Unstructured OCR 并保留原文锚点。"""

import copy
import hashlib
import io
import uuid
import warnings
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .domain import PermanentDocumentError


OCR_LANGUAGES = ["chi_sim", "eng"]
OCR_AGENT = "unstructured.partition.utils.ocr_models.tesseract_ocr.OCRAgentTesseract"
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class EmbeddedImage:
    """描述图片内容及其在原始 Word 正文中的每一次出现。"""

    content: bytes
    sha256: str
    relationship_id: str
    part_name: str
    source_xpath: str
    paragraph_text: str
    occurrence_id: str


# 校验图片真实格式和解码尺寸，防止损坏资源或超大位图进入模型推理。
def _validate_image(content: bytes) -> None:
    from PIL import Image, UnidentifiedImageError

    if len(content) > _MAX_IMAGE_BYTES:
        raise PermanentDocumentError("DOCUMENT_IMAGE_TOO_LARGE", "文档内图片超过20MB限制")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in {"PNG", "JPEG", "TIFF", "BMP", "GIF", "WEBP"}:
                    raise PermanentDocumentError("DOCUMENT_IMAGE_UNSUPPORTED", "文档内图片格式不支持 OCR")
                if image.width * image.height > _MAX_IMAGE_PIXELS:
                    raise PermanentDocumentError("DOCUMENT_IMAGE_TOO_LARGE", "文档内图片超过4000万像素限制")
                if getattr(image, "n_frames", 1) != 1:
                    raise PermanentDocumentError("DOCUMENT_IMAGE_UNSUPPORTED", "文档内多帧图片暂不支持 OCR")
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise PermanentDocumentError("DOCUMENT_IMAGE_INVALID", "文档内图片损坏或无法安全解码") from exc


# 在内存副本中添加可定位占位段落；表格内图片放在表格之后，并保留准确的单元格 XML 路径。
def prepare_docx_images(document: Any) -> Tuple[bytes, Dict[str, EmbeddedImage]]:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    images: Dict[str, EmbeddedImage] = {}
    body = document.element.body
    tree = body.getroottree()
    # 先收集原始位置，避免插入占位段落导致后续图片的 XML 路径发生偏移。
    references = list(body.xpath(".//a:blip | .//*[local-name()='imagedata' and namespace-uri()='urn:schemas-microsoft-com:vml']"))
    positions = [(node, tree.getpath(node)) for node in references]
    anchors: Dict[Any, Any] = {}
    validated = set()
    for index, (node, xpath) in enumerate(positions):
        relationship_id = node.get(qn("r:embed")) or node.get(qn("r:id"))
        if not relationship_id:
            raise PermanentDocumentError("DOCUMENT_IMAGE_EXTERNAL", "文档中的外部链接图片不支持 OCR，请先嵌入图片")
        relationship = document.part.rels.get(relationship_id)
        if relationship is None or relationship.is_external:
            raise PermanentDocumentError("DOCUMENT_IMAGE_EXTERNAL", "文档图片引用无效或指向外部资源")
        part = relationship.target_part
        content = part.blob
        digest = hashlib.sha256(content).hexdigest()
        if digest not in validated:
            _validate_image(content)
            validated.add(digest)
        paragraph = next((parent for parent in node.iterancestors() if parent.tag == qn("w:p")), None)
        paragraph_text = ""
        # 仅取 w:t，避免 lxml 的 itertext 将同一段文字重复计算。
        if paragraph is not None:
            paragraph_text = "".join(text.text or "" for text in paragraph.iter(qn("w:t")))
        anchor = node
        while anchor.getparent() is not body:
            anchor = anchor.getparent()
        marker = "FamilyOS OCR image placeholder %s." % uuid.uuid4().hex
        marker_p = OxmlElement("w:p")
        properties = OxmlElement("w:pPr")
        style = OxmlElement("w:pStyle")
        style.set(qn("w:val"), "Quote")
        properties.append(style)
        marker_p.append(properties)
        run, text = OxmlElement("w:r"), OxmlElement("w:t")
        text.text = marker
        run.append(text)
        marker_p.append(run)
        anchors.get(anchor, anchor).addnext(marker_p)
        anchors[anchor] = marker_p
        images[marker] = EmbeddedImage(content, digest, relationship_id, str(part.partname), xpath, paragraph_text, "docx-image:%d" % index)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue(), images


# 使用与 PDF 相同的高精度模型和 OCR 引擎识别图片，缓存仅在单次文档解析内复用。
def _recognize_image(content: bytes) -> List[Any]:
    from unstructured.partition.image import partition_image

    return partition_image(
        file=io.BytesIO(content), strategy="hi_res", infer_table_structure=True,
        languages=list(OCR_LANGUAGES), ocr_agent=OCR_AGENT, table_ocr_agent=OCR_AGENT,
    )


# 将占位段落替换为 OCR 元素，隔离图片内标题树并恢复文档位置及所属章节。
def expand_docx_images(elements: List[Any], images: Dict[str, EmbeddedImage]) -> List[Any]:
    from unstructured.documents.elements import NarrativeText, Table

    result: List[Any] = []
    cache: Dict[str, List[Any]] = {}
    found = set()
    for element in elements:
        image = images.get(element.text)
        if image is None:
            result.append(element)
            continue
        found.add(element.text)
        if image.sha256 not in cache:
            cache[image.sha256] = _recognize_image(image.content)
        recognized = [item for item in cache[image.sha256] if item.text.strip()]
        for index, item in enumerate(recognized or [None]):
            metadata = copy.deepcopy(item.metadata if item is not None else element.metadata)
            # 图片页码及占位段落页码均不能证明原图片的排版页，来源定位使用原始 XML 锚点。
            metadata.page_number = None
            metadata.parent_id = element.metadata.parent_id
            metadata.filename = element.metadata.filename
            metadata.ocr_source_type = "docx_image"
            metadata.ocr_engine = "tesseract"
            metadata.ocr_languages = list(OCR_LANGUAGES)
            metadata.ocr_status = "recognized" if recognized else "no_text"
            metadata.image_id = image.occurrence_id
            metadata.image_sha256 = image.sha256
            metadata.image_relationship_id = image.relationship_id
            metadata.image_part_name = image.part_name
            metadata.image_source_xpath = image.source_xpath
            metadata.image_paragraph_text = image.paragraph_text
            metadata.coordinate_scope = "embedded_image"
            if item is not None and item.category == "Table":
                metadata.table_parser = "unstructured-image-hi_res"
                metadata.table_header_source = "unconfirmed_first_row"
                if image.paragraph_text:
                    metadata.table_context = image.paragraph_text
            # 图片里的标题不是文档章节，避免污染后续正文的标题路径。
            cls = Table if item is not None and item.category == "Table" else NarrativeText
            result.append(cls(text=item.text if item is not None else "", metadata=metadata, element_id="%s:%d" % (image.occurrence_id, index)))
    if found != images.keys():
        raise PermanentDocumentError("DOCUMENT_IMAGE_POSITION_LOST", "文档图片位置关联失败")
    return result
