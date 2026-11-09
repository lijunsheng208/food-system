"""使用 Unstructured 统一解析 PDF、Word 和 Markdown 文档。"""

import io
import json
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Protocol, Sequence, Tuple

from .domain import DocumentBlock, ParsedDocument, PermanentDocumentError, SourceDocument


class DocumentParser(Protocol):
    """约束所有格式解析器输出统一 ParsedDocument。"""

    # 解析原始文档并保留可用于父子切片的元素树信息。
    def parse(self, source: SourceDocument) -> ParsedDocument:
        ...


_CATEGORY_TYPES = {
    "Title": "heading",
    "ListItem": "list_item",
    "Table": "table",
    "CodeSnippet": "code",
    "NarrativeText": "paragraph",
    "Text": "paragraph",
    "UncategorizedText": "paragraph",
}


# 将 Unstructured 元数据转换为可写入 JSON 数据库字段的值。
def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(key): _json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(item) for item in value]
        return str(value)


# 从解析器 HTML 提取规则网格；合并单元格展开时重复其值，以保留每行的列语义。
def _extract_table(html: Any) -> Dict[str, Any]:
    from bs4 import BeautifulSoup

    result: Dict[str, Any] = {"table_structure_status": "unavailable"}
    if not isinstance(html, str) or not html.strip():
        result["table_structure_error"] = "missing_html"
        return result
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None or table.find("table") is not None:
        return {**result, "table_structure_error": "missing_or_nested_table"}
    rows = []
    occupied: Dict[Tuple[int, int], str] = {}
    header_count = 0
    try:
        source_rows = table.find_all("tr")
        for row_index, tr in enumerate(source_rows):
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells and not any(r == row_index for r, _ in occupied):
                raise ValueError("empty_row")
            if row_index == header_count and (tr.find_parent("thead") is not None or (cells and all(cell.name == "th" for cell in cells))):
                header_count += 1
            column = 0
            for cell in cells:
                while (row_index, column) in occupied:
                    column += 1
                rowspan, colspan = int(cell.get("rowspan", 1)), int(cell.get("colspan", 1))
                if not 1 <= rowspan <= len(source_rows) - row_index or not 1 <= colspan <= 256:
                    raise ValueError("invalid_span")
                value = cell.get_text(" ", strip=True)
                for r in range(row_index, row_index + rowspan):
                    for c in range(column, column + colspan):
                        if (r, c) in occupied:
                            raise ValueError("overlapping_cells")
                        occupied[r, c] = value
                column += colspan
            width = max(c for r, c in occupied if r == row_index) + 1
            rows.append([occupied.get((row_index, c), "") for c in range(width)])
        if not rows or len({len(row) for row in rows}) != 1:
            raise ValueError("irregular_grid")
    except (ValueError, TypeError) as exc:
        return {**result, "table_structure_error": str(exc)}
    caption = table.find("caption")
    return {
        "table_structure_status": "parsed",
        "table_rows": rows,
        "table_header_row_count": header_count,
        "table_title": caption.get_text(" ", strip=True) if caption else "",
    }


class UnstructuredParser:
    """通过 Unstructured partition 输出统一的文档元素树。"""

    # 保存规范化来源格式，供索引元数据追踪解析实现版本。
    def __init__(self, source_format: str) -> None:
        self._source_format = source_format

    # 解析内存文件并把 Unstructured 元素及 parent_id 转为领域模型。
    def parse(self, source: SourceDocument) -> ParsedDocument:
        try:
            elements = self._partition(source)
        except PermanentDocumentError:
            raise
        except Exception as exc:
            raise PermanentDocumentError("DOCUMENT_PARSE_FAILED", "文档解析失败", str(exc)) from exc
        blocks = self._convert_elements(elements)
        if not blocks:
            raise PermanentDocumentError("DOCUMENT_EMPTY", "文档未提取到有效文本")
        title = next((block.text for block in blocks if block.block_type == "heading"), Path(source.filename).stem)
        page_count = max((block.page_number or 0 for block in blocks), default=0)
        metadata: Dict[str, Any] = {
            "source_format": self._source_format,
            "parser_version": "structured-tables-v3",
        }
        if page_count:
            metadata["page_count"] = page_count
        return ParsedDocument(title, blocks, metadata)

    # 延迟导入 Unstructured，避免服务模块加载时触发重型文档依赖初始化。
    def _partition(self, source: SourceDocument) -> Sequence[Any]:
        try:
            from unstructured.partition.auto import partition
        except ImportError as exc:
            raise RuntimeError("缺少 Unstructured 文档解析依赖，请重新安装 agent-python-service") from exc
        # PDF 由专用解析器处理；其余格式继续使用 Unstructured 自动策略。
        strategy = "auto"
        return partition(
            file=io.BytesIO(source.content),
            metadata_filename=source.filename,
            content_type=source.content_type or None,
            include_page_breaks=False,
            strategy=strategy,
        )

    # 转换元素并沿 parent_id 链计算标题路径，保留树结构和页码信息。
    def _convert_elements(self, elements: Sequence[Any]) -> List[DocumentBlock]:
        raw: List[Tuple[str, str, str, Dict[str, Any]]] = []
        for index, element in enumerate(elements):
            text = str(getattr(element, "text", "") or str(element)).strip()
            if not text:
                continue
            category = str(getattr(element, "category", type(element).__name__))
            element_id = str(getattr(element, "element_id", "") or getattr(element, "id", "") or "element-%d" % index)
            metadata_object = getattr(element, "metadata", None)
            metadata_value = metadata_object.to_dict() if metadata_object is not None and hasattr(metadata_object, "to_dict") else {}
            metadata = _json_safe(metadata_value if isinstance(metadata_value, dict) else {})
            parent_id = str(metadata.get("parent_id") or "")
            raw.append((element_id, parent_id, category, {"text": text, **metadata}))

        by_id = {element_id: (parent_id, category, metadata) for element_id, parent_id, category, metadata in raw}
        blocks: List[DocumentBlock] = []
        for element_id, parent_id, category, raw_metadata in raw:
            metadata = dict(raw_metadata)
            text = str(metadata.pop("text"))
            heading_path = self._heading_path(parent_id, by_id)
            if category == "Title":
                heading_path = heading_path + (text,)
            depth = metadata.get("category_depth")
            heading_level = min(max(depth + 1, 1), 6) if category == "Title" and isinstance(depth, int) else (1 if category == "Title" else None)
            page_number = metadata.get("page_number")
            if isinstance(page_number, str) and page_number.isdigit():
                page_number = int(page_number)
            if category == "Table":
                metadata.update(_extract_table(metadata.get("text_as_html")))
                if metadata.get("table_structure_status") == "parsed" and metadata.get("table_header_source") == "word_repeat_header":
                    metadata["table_header_row_count"] = metadata["word_header_row_count"]
                # Markdown 管道表语法保证首行为表头，但 Unstructured 会将其输出为 td。
                if self._source_format == "markdown" and metadata.get("table_structure_status") == "parsed" and not metadata["table_header_row_count"]:
                    metadata["table_header_row_count"] = 1
                    metadata["table_header_source"] = "markdown_first_row"
                metadata["table_id"] = element_id
                # 仅携带同章节紧邻的说明，保留表外单位和适用条件，不猜测数值含义。
                if blocks and blocks[-1].block_type == "paragraph" and blocks[-1].heading_path == heading_path:
                    metadata["table_context"] = blocks[-1].text
            blocks.append(DocumentBlock(
                _CATEGORY_TYPES.get(category, category.lower()),
                text,
                len(blocks),
                heading_level,
                heading_path,
                int(page_number) if isinstance(page_number, int) else None,
                {"unstructured_category": category, **metadata},
                element_id,
                parent_id,
            ))
        return blocks

    # 沿元素父链收集 Title 文本，并防止异常文档中的循环引用。
    def _heading_path(self, parent_id: str, by_id: Dict[str, Tuple[str, str, Dict[str, Any]]]) -> Tuple[str, ...]:
        headings: List[str] = []
        visited = set()
        current = parent_id
        while current and current not in visited:
            visited.add(current)
            node = by_id.get(current)
            if node is None:
                break
            current, category, metadata = node
            if category == "Title":
                headings.append(str(metadata["text"]))
        headings.reverse()
        return tuple(headings)


class MarkdownParser(UnstructuredParser):
    """使用 Unstructured 解析 Markdown 元素树。"""

    # 初始化 Markdown 来源标识。
    def __init__(self) -> None:
        super().__init__("markdown")


class DocxParser(UnstructuredParser):
    """使用 Unstructured 解析 DOC 和 DOCX 元素树。"""

    # 初始化 Word 来源标识。
    def __init__(self) -> None:
        super().__init__("word")

    # DOCX 显式开启结构提取，并读取 Word 重复标题行标记；旧 DOC 继续交由现有转换链处理。
    def _partition(self, source: SourceDocument) -> Sequence[Any]:
        if Path(source.filename).suffix.lower() != ".docx":
            return super()._partition(source)
        from docx import Document
        from docx.oxml.ns import qn
        from unstructured.partition.docx import partition_docx

        elements = partition_docx(file=io.BytesIO(source.content), infer_table_structure=True)
        tables = Document(io.BytesIO(source.content)).tables
        extracted = [element for element in elements if element.category == "Table"]
        if len(tables) != len(extracted):
            raise ValueError("Word 表格数量与解析输出不一致，无法可靠关联来源")
        for table, element in zip(tables, extracted):
            headers = 0
            for row in table.rows:
                marker = row._tr.find("./" + qn("w:trPr") + "/" + qn("w:tblHeader"))
                if marker is None or marker.get(qn("w:val"), "true").lower() in ("0", "false", "off"):
                    break
                headers += 1
            element.metadata.word_header_row_count = headers
            if headers:
                element.metadata.table_header_source = "word_repeat_header"
            # Unstructured 的 HTML 是规范化表示，原始 OOXML 用于追溯合并单元格等来源信息。
            element.metadata.table_source_xml = table._tbl.xml
        return elements


class PdfParser(UnstructuredParser):
    """使用 pdfplumber 提取文字型 PDF 的有线表格和正文，不执行 OCR。"""

    # 初始化 PDF 来源标识。
    def __init__(self) -> None:
        super().__init__("pdf")

    # 以表格边界分离正文，避免同一行表格数据再次作为普通段落进入索引。
    def _partition(self, source: SourceDocument) -> Sequence[Any]:
        import pdfplumber
        from unstructured.documents.elements import ElementMetadata, NarrativeText, Table

        elements: List[Any] = []
        with pdfplumber.open(io.BytesIO(source.content)) as pdf:
            for page_number, page in enumerate(pdf.pages, 1):
                tables = [
                    table for table in page.find_tables()
                    if len(table.rows) >= 2 and len(table.columns) >= 2
                    and any(cell and cell.strip() for row in table.extract() for cell in row)
                ]
                items = []
                for index, table in enumerate(tables):
                    html = _pdf_table_html(table)
                    metadata = ElementMetadata(page_number=page_number, text_as_html=html)
                    metadata.table_bbox = list(table.bbox)
                    metadata.table_parser = "pdfplumber-lines"
                    # PDF 没有可靠的表头语义，只作为候选上下文重复首行，不从数据行范围中删除。
                    metadata.table_header_source = "unconfirmed_first_row"
                    element = Table(text="\n".join(" | ".join(cell or "" for cell in row) for row in table.extract()), element_id="pdf:%d:table:%d" % (page_number, index), metadata=metadata)
                    items.append((table.bbox[1], table.bbox[0], element))
                words = page.extract_words()
                lines: Dict[float, List[Dict[str, Any]]] = {}
                for word in words:
                    x, y = (word["x0"] + word["x1"]) / 2, (word["top"] + word["bottom"]) / 2
                    if any(left <= x <= right and top <= y <= bottom for left, top, right, bottom in (table.bbox for table in tables)):
                        continue
                    key = round(word["top"] / 3) * 3
                    lines.setdefault(key, []).append(word)
                for top, line in lines.items():
                    line.sort(key=lambda word: word["x0"])
                    items.append((top, line[0]["x0"], NarrativeText(text=" ".join(word["text"] for word in line), metadata=ElementMetadata(page_number=page_number))))
                elements.extend(item[2] for item in sorted(items, key=lambda item: (item[0], item[1])))
        if not elements:
            raise PermanentDocumentError("PDF_TEXT_UNAVAILABLE", "PDF 未提取到文字，扫描件需单独进行 OCR")
        return elements


# 根据实际单元格坐标重建跨度，不将合并单元格误当作空白数据。
def _pdf_table_html(table: Any) -> str:
    xs = sorted({value for cell in table.cells for value in (cell[0], cell[2])})
    ys = sorted({value for cell in table.cells for value in (cell[1], cell[3])})
    rows: Dict[float, List[Tuple[float, str]]] = {y: [] for y in ys[:-1]}
    for row, values in zip(table.rows, table.extract()):
        for cell, value in zip(row.cells, values):
            if cell is None:
                continue
            left, top, right, bottom = cell
            colspan, rowspan = xs.index(right) - xs.index(left), ys.index(bottom) - ys.index(top)
            rows[top].append((left, '<td colspan="%d" rowspan="%d">%s</td>' % (colspan, rowspan, escape(value or ""))))
    return "<table>" + "".join("<tr>" + "".join(cell for _, cell in sorted(rows[y])) + "</tr>" for y in ys[:-1]) + "</table>"


class ParserRegistry:
    """根据文件扩展名选择 Unstructured 解析器。"""

    # 注册 FamilyOS 当前承诺支持的 Markdown、Word 和 PDF 格式。
    def __init__(self) -> None:
        markdown = MarkdownParser()
        word = DocxParser()
        self._parsers: Dict[str, DocumentParser] = {
            ".md": markdown,
            ".markdown": markdown,
            ".doc": word,
            ".docx": word,
            ".pdf": PdfParser(),
        }

    # 优先使用票据扩展名，并在缺失时从原始文件名推断格式。
    def resolve(self, extension: str, filename: str) -> DocumentParser:
        normalized = extension.strip().lower() or Path(filename).suffix.lower()
        if normalized and not normalized.startswith("."):
            normalized = "." + normalized
        parser = self._parsers.get(normalized)
        if parser is None:
            raise PermanentDocumentError("UNSUPPORTED_FILE_TYPE", "文件类型不支持", normalized)
        return parser
