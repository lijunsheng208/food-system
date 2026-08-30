package embedding

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const maxEmbeddingResponseBytes = 16 << 20

// OpenAICompatibleConfig 描述 OpenAI-compatible Embedding 接口参数。
type OpenAICompatibleConfig struct {
	BaseURL         string
	APIKey          string
	Model           string
	DimensionsValue int
	BatchSize       int
	Timeout         time.Duration
}

// OpenAICompatible 调用 OpenAI-compatible /embeddings 接口。
type OpenAICompatible struct {
	config OpenAICompatibleConfig
	client *http.Client
}

type embeddingRequest struct {
	Model      string   `json:"model"`
	Input      []string `json:"input"`
	Dimensions int      `json:"dimensions,omitempty"`
}
type embeddingDatum struct {
	Embedding []float32 `json:"embedding"`
	Index     int       `json:"index"`
}
type embeddingResponse struct {
	Data  []embeddingDatum `json:"data"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error,omitempty"`
}

// NewOpenAICompatible 创建带超时和批量限制的 Embedding 客户端。
func NewOpenAICompatible(config OpenAICompatibleConfig) (*OpenAICompatible, error) {
	if config.BaseURL == "" || config.APIKey == "" || config.Model == "" || config.DimensionsValue <= 0 || config.BatchSize <= 0 || config.Timeout <= 0 {
		return nil, fmt.Errorf("Embedding 配置无效")
	}
	config.BaseURL = strings.TrimSuffix(config.BaseURL, "/")
	return &OpenAICompatible{config: config, client: &http.Client{Timeout: config.Timeout}}, nil
}

// EmbedDocuments 分批生成文档向量并保持输入顺序。
func (e *OpenAICompatible) EmbedDocuments(ctx context.Context, texts []string) ([][]float32, error) {
	result := make([][]float32, 0, len(texts))
	for start := 0; start < len(texts); start += e.config.BatchSize {
		end := start + e.config.BatchSize
		if end > len(texts) {
			end = len(texts)
		}
		vectors, err := e.embed(ctx, texts[start:end])
		if err != nil {
			return nil, err
		}
		result = append(result, vectors...)
	}
	return result, nil
}

// EmbedQuery 为检索文本生成单个向量。
func (e *OpenAICompatible) EmbedQuery(ctx context.Context, text string) ([]float32, error) {
	vectors, err := e.embed(ctx, []string{text})
	if err != nil {
		return nil, err
	}
	return vectors[0], nil
}

// Dimensions 返回配置的向量维度。
func (e *OpenAICompatible) Dimensions() int { return e.config.DimensionsValue }

// embed 执行单次 HTTP 请求并严格校验数量、顺序和向量维度。
func (e *OpenAICompatible) embed(ctx context.Context, texts []string) ([][]float32, error) {
	if len(texts) == 0 {
		return nil, nil
	}
	payload, err := json.Marshal(embeddingRequest{Model: e.config.Model, Input: texts, Dimensions: e.config.DimensionsValue})
	if err != nil {
		return nil, fmt.Errorf("编码 Embedding 请求失败: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, e.config.BaseURL+"/embeddings", bytes.NewReader(payload))
	if err != nil {
		return nil, fmt.Errorf("创建 Embedding 请求失败: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Authorization", "Bearer "+e.config.APIKey)
	response, err := e.client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("请求 Embedding 服务失败: %w", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, maxEmbeddingResponseBytes+1))
	if err != nil {
		return nil, fmt.Errorf("读取 Embedding 响应失败: %w", err)
	}
	if len(body) > maxEmbeddingResponseBytes {
		return nil, fmt.Errorf("Embedding 响应超过大小限制")
	}
	var decoded embeddingResponse
	if err := json.Unmarshal(body, &decoded); err != nil {
		return nil, fmt.Errorf("解析 Embedding 响应失败: %w", err)
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, fmt.Errorf("Embedding 服务返回 HTTP %d", response.StatusCode)
	}
	if len(decoded.Data) != len(texts) {
		return nil, fmt.Errorf("%w: 数量不匹配 got=%d want=%d", ErrInvalidEmbeddingResponse, len(decoded.Data), len(texts))
	}
	vectors := make([][]float32, len(texts))
	for _, item := range decoded.Data {
		if item.Index < 0 || item.Index >= len(texts) || vectors[item.Index] != nil {
			return nil, fmt.Errorf("%w: 响应索引无效", ErrInvalidEmbeddingResponse)
		}
		if len(item.Embedding) != e.config.DimensionsValue {
			return nil, fmt.Errorf("%w: 维度不匹配 got=%d want=%d", ErrInvalidEmbeddingResponse, len(item.Embedding), e.config.DimensionsValue)
		}
		vectors[item.Index] = item.Embedding
	}
	return vectors, nil
}
