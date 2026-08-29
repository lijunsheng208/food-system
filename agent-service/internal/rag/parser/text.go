package parser

import (
	"bytes"
	"context"
	"encoding/binary"
	"io"
	"strings"
	"unicode/utf16"
	"unicode/utf8"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// Text 解析 UTF-8 或带 BOM 的 UTF-16 纯文本。
type Text struct{}

// Parse 读取纯文本并转换为 UTF-8。
func (Text) Parse(_ context.Context, reader io.Reader, _ document.SourceDocument) (*document.ParsedDocument, error) {
	data, err := io.ReadAll(reader)
	if err != nil {
		return nil, err
	}
	text := decodeText(data)
	return &document.ParsedDocument{Text: strings.TrimSpace(text), Metadata: map[string]any{}}, nil
}

// decodeText 参考 LightningRAG 的文本解析逻辑处理 UTF-16 BOM 和非法 UTF-8。
func decodeText(data []byte) string {
	if len(data) >= 2 && data[0] == 0xff && data[1] == 0xfe {
		return decodeUTF16(data[2:], binary.LittleEndian)
	}
	if len(data) >= 2 && data[0] == 0xfe && data[1] == 0xff {
		return decodeUTF16(data[2:], binary.BigEndian)
	}
	if !utf8.Valid(data) {
		data = bytes.ToValidUTF8(data, []byte(" "))
	}
	return string(data)
}

// decodeUTF16 将指定字节序的 UTF-16 字节转换为字符串。
func decodeUTF16(data []byte, order binary.ByteOrder) string {
	if len(data)%2 != 0 {
		data = data[:len(data)-1]
	}
	values := make([]uint16, len(data)/2)
	for i := range values {
		values[i] = order.Uint16(data[i*2:])
	}
	return string(utf16.Decode(values))
}
