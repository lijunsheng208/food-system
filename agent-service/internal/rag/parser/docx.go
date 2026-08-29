package parser

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"strings"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// DOCX 从 Office Open XML 文档主体中提取段落文本。
type DOCX struct{}

// Parse 解压 DOCX 并解析 word/document.xml。
func (DOCX) Parse(_ context.Context, reader io.Reader, _ document.SourceDocument) (*document.ParsedDocument, error) {
	data, err := io.ReadAll(reader)
	if err != nil {
		return nil, fmt.Errorf("读取 DOCX 失败: %w", err)
	}
	archive, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, fmt.Errorf("DOCX 不是有效 ZIP: %w", err)
	}
	for _, file := range archive.File {
		if file.Name != "word/document.xml" {
			continue
		}
		stream, openErr := file.Open()
		if openErr != nil {
			return nil, fmt.Errorf("打开 DOCX 主体失败: %w", openErr)
		}
		text, parseErr := extractDOCXText(stream)
		_ = stream.Close()
		if parseErr != nil {
			return nil, parseErr
		}
		if strings.TrimSpace(text) == "" {
			return nil, fmt.Errorf("DOCX 未提取到文本")
		}
		return &document.ParsedDocument{Text: strings.TrimSpace(text), Metadata: map[string]any{}}, nil
	}
	return nil, fmt.Errorf("DOCX 缺少 word/document.xml")
}

// extractDOCXText 按段落、换行和制表符提取 WordprocessingML 文本。
func extractDOCXText(reader io.Reader) (string, error) {
	decoder := xml.NewDecoder(reader)
	var output strings.Builder
	for {
		token, err := decoder.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return "", fmt.Errorf("解析 DOCX XML 失败: %w", err)
		}
		switch value := token.(type) {
		case xml.CharData:
			output.Write([]byte(value))
		case xml.StartElement:
			if value.Name.Local == "tab" {
				output.WriteByte('\t')
			}
			if value.Name.Local == "br" {
				output.WriteByte('\n')
			}
		case xml.EndElement:
			if value.Name.Local == "p" {
				output.WriteByte('\n')
			}
		}
	}
	return output.String(), nil
}
