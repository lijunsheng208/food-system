package parser

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"strings"

	"github.com/ledongthuc/pdf"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// PDF 使用纯 Go PDF 解析器逐页提取文本。
type PDF struct{}

// Parse 从 PDF 字节中提取正文，并记录页数元数据。
func (PDF) Parse(_ context.Context, reader io.Reader, _ document.SourceDocument) (*document.ParsedDocument, error) {
	data, err := io.ReadAll(reader)
	if err != nil {
		return nil, fmt.Errorf("读取 PDF 失败: %w", err)
	}
	r, err := pdf.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, fmt.Errorf("解析 PDF 失败: %w", err)
	}
	var output strings.Builder
	for pageNumber := 1; pageNumber <= r.NumPage(); pageNumber++ {
		page := r.Page(pageNumber)
		if page.V.IsNull() {
			continue
		}
		text, pageErr := page.GetPlainText(nil)
		if pageErr != nil {
			return nil, fmt.Errorf("提取 PDF 第 %d 页失败: %w", pageNumber, pageErr)
		}
		text = strings.TrimSpace(text)
		if text == "" {
			continue
		}
		if output.Len() > 0 {
			output.WriteString("\n\n")
		}
		output.WriteString(text)
	}
	if strings.TrimSpace(output.String()) == "" {
		return nil, fmt.Errorf("PDF 未提取到文本，可能是扫描件")
	}
	return &document.ParsedDocument{Text: strings.TrimSpace(output.String()), Metadata: map[string]any{"page_count": r.NumPage()}}, nil
}
