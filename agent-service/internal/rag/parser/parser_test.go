package parser

import (
	"archive/zip"
	"bytes"
	"context"
	"testing"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// TestTextParseUTF16LE 验证文本解析器兼容带 BOM 的 UTF-16LE。
func TestTextParseUTF16LE(t *testing.T) {
	parsed, err := (Text{}).Parse(context.Background(), bytes.NewReader([]byte{0xff, 0xfe, 'A', 0, 0x2d, 0x4e}), document.SourceDocument{})
	if err != nil {
		t.Fatalf("解析 UTF-16 失败: %v", err)
	}
	if parsed.Text != "A中" {
		t.Fatalf("文本 = %q", parsed.Text)
	}
}

// TestDOCXParse 验证 DOCX 主体段落可以提取为文本。
func TestDOCXParse(t *testing.T) {
	var data bytes.Buffer
	writer := zip.NewWriter(&data)
	part, err := writer.Create("word/document.xml")
	if err != nil {
		t.Fatal(err)
	}
	_, _ = part.Write([]byte(`<w:document xmlns:w="x"><w:body><w:p><w:r><w:t>第一段</w:t></w:r></w:p><w:p><w:r><w:t>第二段</w:t></w:r></w:p></w:body></w:document>`))
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	parsed, err := (DOCX{}).Parse(context.Background(), bytes.NewReader(data.Bytes()), document.SourceDocument{})
	if err != nil {
		t.Fatalf("解析 DOCX 失败: %v", err)
	}
	if parsed.Text != "第一段\n第二段" {
		t.Fatalf("文本 = %q", parsed.Text)
	}
}

// TestRegistryRejectsUnsupportedExtension 验证注册表拒绝未开放格式。
func TestRegistryRejectsUnsupportedExtension(t *testing.T) {
	if _, err := NewRegistry().Resolve(".xlsx", "test.xlsx"); err == nil {
		t.Fatal("期望拒绝 xlsx")
	}
}
