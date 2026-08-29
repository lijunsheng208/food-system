package parser

import (
	"context"
	"io"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// Markdown 保留 Markdown 标题和列表结构，供后续语义切片使用。
type Markdown struct{}

// Parse 将 Markdown 规范化为 UTF-8 文本，但不剥离结构标记。
func (Markdown) Parse(ctx context.Context, reader io.Reader, source document.SourceDocument) (*document.ParsedDocument, error) {
	return (Text{}).Parse(ctx, reader, source)
}
