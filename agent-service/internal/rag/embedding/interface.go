package embedding

import "context"

// Embedder 为文档和查询生成相同维度的向量。
type Embedder interface {
	EmbedDocuments(ctx context.Context, texts []string) ([][]float32, error)
	EmbedQuery(ctx context.Context, text string) ([]float32, error)
	Dimensions() int
}
