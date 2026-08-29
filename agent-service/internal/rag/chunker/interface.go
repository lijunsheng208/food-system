package chunker

import (
	"context"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// Chunker 将解析后的长文本切分为可生成向量的稳定片段。
type Chunker interface {
	Chunk(ctx context.Context, source document.SourceDocument, parsed *document.ParsedDocument) ([]document.Chunk, error)
}
