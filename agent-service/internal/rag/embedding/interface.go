package embedding

import (
	"context"
	"errors"
)

// ErrInvalidEmbeddingResponse 表示服务返回的向量结构与索引配置不兼容。
var ErrInvalidEmbeddingResponse = errors.New("Embedding 响应结构无效")

// Embedder 为文档和查询生成相同维度的向量。
type Embedder interface {
	EmbedDocuments(ctx context.Context, texts []string) ([][]float32, error)
	EmbedQuery(ctx context.Context, text string) ([]float32, error)
	Dimensions() int
}
