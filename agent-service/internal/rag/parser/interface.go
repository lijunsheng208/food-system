package parser

import (
	"context"
	"io"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// Parser 将一种文档格式转换为规范化文本。
type Parser interface {
	Parse(ctx context.Context, reader io.Reader, source document.SourceDocument) (*document.ParsedDocument, error)
}
