package vectorstore

import (
	"context"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// Store 持久化文档向量，并提供受知识库边界约束的相似度检索。
type Store interface {
	ReplaceDocumentVersion(ctx context.Context, documentID uint64, indexVersion uint, chunks []document.EmbeddedChunk) error
	DeleteDocumentVersion(ctx context.Context, documentID uint64, indexVersion uint) error
	Search(ctx context.Context, query []float32, filter document.SearchFilter) ([]document.SearchResult, error)
}
