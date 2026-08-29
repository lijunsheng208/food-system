package search

import (
	"context"
	"fmt"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/embedding"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/vectorstore"
)

// Retriever 将查询文本向量化，并在指定知识库内检索活动索引版本。
type Retriever struct {
	embedder embedding.Embedder
	store    vectorstore.Store
}

// NewRetriever 创建语义检索器。
func NewRetriever(embedder embedding.Embedder, store vectorstore.Store) (*Retriever, error) {
	if embedder == nil || store == nil {
		return nil, fmt.Errorf("检索器依赖不能为空")
	}
	return &Retriever{embedder: embedder, store: store}, nil
}

// Search 在调用方已经完成知识库权限校验后执行向量检索。
func (r *Retriever) Search(ctx context.Context, query string, filter document.SearchFilter) ([]document.SearchResult, error) {
	if query == "" || filter.KnowledgeBaseID == 0 {
		return nil, fmt.Errorf("检索参数无效")
	}
	vector, err := r.embedder.EmbedQuery(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("生成查询向量失败: %w", err)
	}
	return r.store.Search(ctx, vector, filter)
}
