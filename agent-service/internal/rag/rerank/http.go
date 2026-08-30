package rerank

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// HTTPConfig 描述兼容 DashScope OpenAI 接口的文本重排连接参数。
type HTTPConfig struct {
	BaseURL string
	APIKey  string
	Model   string
	Timeout time.Duration
	TopK    int
}

// HTTPReranker 通过 HTTP Cross-Encoder 服务对候选切片重排序。
type HTTPReranker struct {
	endpoint string
	apiKey   string
	model    string
	topK     int
	client   *http.Client
}

type request struct {
	Model     string   `json:"model"`
	Query     string   `json:"query"`
	Documents []string `json:"documents"`
	TopN      int      `json:"top_n,omitempty"`
}

type response struct {
	Results []struct {
		Index          int     `json:"index"`
		RelevanceScore float32 `json:"relevance_score"`
	} `json:"results"`
}

// NewHTTP 创建 DashScope Cross-Encoder HTTP 客户端。
func NewHTTP(config HTTPConfig) (*HTTPReranker, error) {
	if strings.TrimSpace(config.BaseURL) == "" || strings.TrimSpace(config.APIKey) == "" || strings.TrimSpace(config.Model) == "" || config.Timeout <= 0 || config.TopK <= 0 || config.TopK > 100 {
		return nil, fmt.Errorf("rerank HTTP 配置无效")
	}
	return &HTTPReranker{endpoint: strings.TrimRight(config.BaseURL, "/") + "/reranks", apiKey: config.APIKey, model: config.Model, topK: config.TopK, client: &http.Client{Timeout: config.Timeout}}, nil
}

// Rerank 调用远端 Cross-Encoder，并按返回的候选索引重建结果顺序。
func (r *HTTPReranker) Rerank(ctx context.Context, query string, candidates []document.SearchResult) ([]document.SearchResult, error) {
	if strings.TrimSpace(query) == "" || len(candidates) == 0 {
		return nil, fmt.Errorf("rerank 参数无效")
	}
	documents := make([]string, len(candidates))
	for i := range candidates {
		documents[i] = candidates[i].Content
	}
	topN := r.topK
	if topN > len(candidates) {
		topN = len(candidates)
	}
	body, err := json.Marshal(request{Model: r.model, Query: query, Documents: documents, TopN: topN})
	if err != nil {
		return nil, fmt.Errorf("序列化 rerank 请求失败: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, r.endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("创建 rerank 请求失败: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+r.apiKey)
	resp, err := r.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("调用 rerank 服务失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("rerank 服务返回 HTTP %d", resp.StatusCode)
	}
	var decoded response
	if err := json.NewDecoder(resp.Body).Decode(&decoded); err != nil {
		return nil, fmt.Errorf("解析 rerank 响应失败: %w", err)
	}
	results := make([]document.SearchResult, 0, len(decoded.Results))
	seen := make(map[int]struct{}, len(decoded.Results))
	for _, item := range decoded.Results {
		if item.Index < 0 || item.Index >= len(candidates) {
			return nil, fmt.Errorf("rerank 响应包含无效候选索引")
		}
		if _, ok := seen[item.Index]; ok {
			return nil, fmt.Errorf("rerank 响应包含重复候选索引")
		}
		seen[item.Index] = struct{}{}
		candidate := candidates[item.Index]
		candidate.Score = item.RelevanceScore
		results = append(results, candidate)
	}
	if len(results) == 0 {
		return nil, fmt.Errorf("rerank 响应没有候选结果")
	}
	return results, nil
}
