package search

import (
	"context"
	"fmt"
	"sort"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/embedding"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/lexical"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/rerank"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/vectorstore"
)

// HybridRetriever 同时执行 Dense 和 BM25 检索，并用加权 RRF 合并候选结果。
type HybridRetriever struct {
	dense         *Retriever
	lexical       lexical.Retriever
	denseWeight   float64
	lexicalWeight float64
	constant      float64
	candidateK    int
	reranker      rerank.Reranker
}

// HybridConfig 描述混合检索的权重、平滑常数和候选数量。
type HybridConfig struct {
	DenseWeight   float64
	LexicalWeight float64
	Constant      float64
	CandidateK    int
	Reranker      rerank.Reranker
}

// NewHybridRetriever 创建混合检索器，权重必须为正且候选数量受控。
func NewHybridRetriever(embedder embedding.Embedder, store vectorstore.Store, lexicalStore lexical.Retriever, config HybridConfig) (*HybridRetriever, error) {
	if lexicalStore == nil || config.DenseWeight <= 0 || config.LexicalWeight <= 0 || config.Constant <= 0 || config.CandidateK <= 0 || config.CandidateK > 100 {
		return nil, fmt.Errorf("混合检索配置无效")
	}
	dense, err := NewRetriever(embedder, store)
	if err != nil {
		return nil, err
	}
	return &HybridRetriever{dense: dense, lexical: lexicalStore, denseWeight: config.DenseWeight, lexicalWeight: config.LexicalWeight, constant: config.Constant, candidateK: config.CandidateK, reranker: config.Reranker}, nil
}

// Search 执行两路检索并按 Chunk ID 融合，返回调用方要求的 TopK。
func (r *HybridRetriever) Search(ctx context.Context, query string, filter document.SearchFilter) ([]document.SearchResult, error) {
	if query == "" || filter.KnowledgeBaseID == 0 || filter.Limit <= 0 || filter.Limit > 100 {
		return nil, fmt.Errorf("混合检索参数无效")
	}
	dense, err := r.dense.Search(ctx, query, document.SearchFilter{KnowledgeBaseID: filter.KnowledgeBaseID, DocumentID: filter.DocumentID, Limit: r.candidateK})
	if err != nil {
		return nil, err
	}
	lexicalResults, err := r.lexical.Search(ctx, query, document.SearchFilter{KnowledgeBaseID: filter.KnowledgeBaseID, DocumentID: filter.DocumentID, Limit: r.candidateK})
	if err != nil {
		return nil, fmt.Errorf("BM25 检索失败: %w", err)
	}
	type scored struct {
		result document.SearchResult
		score  float64
	}
	merged := make(map[string]scored, len(dense)+len(lexicalResults))
	for rank, result := range dense {
		item := merged[result.ID]
		item.result = result
		item.score += r.denseWeight / (r.constant + float64(rank+1))
		merged[result.ID] = item
	}
	for rank, result := range lexicalResults {
		item := merged[result.ID]
		if item.result.ID == "" {
			item.result = result
		}
		item.score += r.lexicalWeight / (r.constant + float64(rank+1))
		merged[result.ID] = item
	}
	items := make([]scored, 0, len(merged))
	for _, item := range merged {
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].score == items[j].score {
			return items[i].result.ID < items[j].result.ID
		}
		return items[i].score > items[j].score
	})
	if len(items) > r.candidateK {
		items = items[:r.candidateK]
	}
	results := make([]document.SearchResult, len(items))
	for i, item := range items {
		item.result.Score = float32(item.score)
		results[i] = item.result
	}
	if r.reranker != nil {
		ranked, err := r.reranker.Rerank(ctx, query, results)
		if err != nil {
			return nil, fmt.Errorf("Cross-Encoder 重排失败: %w", err)
		}
		results = ranked
	}
	if len(results) > filter.Limit {
		results = results[:filter.Limit]
	}
	return results, nil
}
