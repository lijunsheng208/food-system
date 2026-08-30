package rerank

import (
	"context"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// Reranker 对第一阶段召回的候选文档进行精细化排序。
type Reranker interface {
	Rerank(context.Context, string, []document.SearchResult) ([]document.SearchResult, error)
}
