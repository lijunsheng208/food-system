package lexical

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
	"github.com/opensearch-project/opensearch-go/v2"
)

// Retriever 定义 BM25 词法索引的写入和检索能力。
type Retriever interface {
	IndexVersion(context.Context, uint64, uint, []document.Chunk) error
	DeleteVersion(context.Context, uint64, uint) error
	Search(context.Context, string, document.SearchFilter) ([]document.SearchResult, error)
}

// Config 描述 OpenSearch 连接和索引配置。
type Config struct {
	Endpoint       string
	Username       string
	Password       string
	Index          string
	RequestTimeout time.Duration
}

// OpenSearch 使用 IK 分词器和标准 BM25 相似度保存 Chunk 倒排索引。
type OpenSearch struct {
	client   *opensearch.Client
	endpoint string
	index    string
	timeout  time.Duration
}

// sourceChunk 描述 OpenSearch 返回的下划线字段，避免直接映射到 Go 字段失败。
type sourceChunk struct {
	ID              string `json:"chunk_id"`
	DocumentID      uint64 `json:"document_id"`
	KnowledgeBaseID uint64 `json:"knowledge_base_id"`
	UserID          uint64 `json:"user_id"`
	IndexVersion    uint   `json:"index_version"`
	Content         string `json:"content"`
	ContentSHA256   string `json:"content_sha256"`
}

// NewOpenSearch 创建客户端并确保目标索引存在。
func NewOpenSearch(config Config) (*OpenSearch, error) {
	if config.Endpoint == "" || config.Index == "" || config.RequestTimeout <= 0 {
		return nil, fmt.Errorf("OpenSearch 配置无效")
	}
	client, err := opensearch.NewClient(opensearch.Config{Addresses: []string{config.Endpoint}, Username: config.Username, Password: config.Password})
	if err != nil {
		return nil, fmt.Errorf("创建 OpenSearch 客户端失败: %w", err)
	}
	store := &OpenSearch{client: client, endpoint: strings.TrimRight(config.Endpoint, "/"), index: config.Index, timeout: config.RequestTimeout}
	if err := store.ensureIndex(context.Background()); err != nil {
		return nil, err
	}
	return store, nil
}

// ensureIndex 创建 IK 分词和 BM25 索引，已存在时保持幂等。
func (s *OpenSearch) ensureIndex(ctx context.Context) error {
	body := `{"settings":{"index":{"similarity":{"default":{"type":"BM25","k1":1.2,"b":0.75}},"analysis":{"analyzer":{"familyos_index":{"type":"custom","tokenizer":"ik_max_word","filter":["lowercase"]},"familyos_search":{"type":"custom","tokenizer":"ik_smart","filter":["lowercase"]}}}},"mappings":{"properties":{"chunk_id":{"type":"keyword"},"document_id":{"type":"long"},"knowledge_base_id":{"type":"long"},"user_id":{"type":"long"},"index_version":{"type":"integer"},"active":{"type":"boolean"},"content":{"type":"text","analyzer":"familyos_index","search_analyzer":"familyos_search"},"content_sha256":{"type":"keyword"}}}}`
	request, err := http.NewRequestWithContext(ctx, http.MethodPut, s.endpoint+"/"+s.index, bytes.NewBufferString(body))
	if err != nil {
		return fmt.Errorf("创建 OpenSearch 索引请求失败: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := s.client.Transport.Perform(request)
	if err != nil {
		return fmt.Errorf("创建 OpenSearch 索引失败: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode >= 300 && response.StatusCode != http.StatusBadRequest {
		data, _ := io.ReadAll(response.Body)
		return fmt.Errorf("创建 OpenSearch 索引返回 HTTP %d: %s", response.StatusCode, string(data))
	}
	return nil
}

// IndexVersion 通过 Bulk API 幂等写入一个文档版本的全部 Chunk。
func (s *OpenSearch) IndexVersion(ctx context.Context, documentID uint64, version uint, chunks []document.Chunk) error {
	if documentID == 0 || version == 0 || len(chunks) == 0 {
		return fmt.Errorf("OpenSearch 索引数据无效")
	}
	var body bytes.Buffer
	for _, chunk := range chunks {
		if chunk.ID == "" || chunk.Content == "" || chunk.DocumentID != documentID || chunk.IndexVersion != version {
			return fmt.Errorf("OpenSearch Chunk 数据无效")
		}
		meta, _ := json.Marshal(map[string]any{"index": map[string]any{"_id": chunk.ID}})
		doc, _ := json.Marshal(map[string]any{"chunk_id": chunk.ID, "document_id": chunk.DocumentID, "knowledge_base_id": chunk.KnowledgeBaseID, "user_id": chunk.UserID, "index_version": chunk.IndexVersion, "active": true, "content": chunk.Content, "content_sha256": chunk.ContentSHA256})
		body.Write(meta)
		body.WriteByte('\n')
		body.Write(doc)
		body.WriteByte('\n')
	}
	request, err := s.newRequest(ctx, http.MethodPost, "/_bulk", &body)
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/x-ndjson")
	response, err := s.client.Transport.Perform(request)
	if err != nil {
		return fmt.Errorf("OpenSearch Bulk 写入失败: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode >= 300 {
		return fmt.Errorf("OpenSearch Bulk 写入返回 HTTP %d", response.StatusCode)
	}
	var result struct {
		Errors bool `json:"errors"`
	}
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		return fmt.Errorf("解析 OpenSearch Bulk 响应失败: %w", err)
	}
	if result.Errors {
		return fmt.Errorf("OpenSearch Bulk 部分 Chunk 写入失败")
	}
	return nil
}

// DeleteVersion 删除指定文档版本的词法索引。
func (s *OpenSearch) DeleteVersion(ctx context.Context, documentID uint64, version uint) error {
	query := map[string]any{"query": map[string]any{"bool": map[string]any{"filter": []any{map[string]any{"term": map[string]any{"document_id": documentID}}, map[string]any{"term": map[string]any{"index_version": version}}}}}}
	data, _ := json.Marshal(query)
	request, err := s.newRequest(ctx, http.MethodPost, "/_delete_by_query", bytes.NewReader(data))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := s.client.Transport.Perform(request)
	if err != nil {
		return fmt.Errorf("删除 OpenSearch 版本失败: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode >= 300 {
		return fmt.Errorf("删除 OpenSearch 版本返回 HTTP %d", response.StatusCode)
	}
	return nil
}

// Search 在知识库活动版本内执行 IK 分词 BM25 查询。
func (s *OpenSearch) Search(ctx context.Context, query string, filter document.SearchFilter) ([]document.SearchResult, error) {
	if strings.TrimSpace(query) == "" || filter.KnowledgeBaseID == 0 || filter.Limit <= 0 || filter.Limit > 100 {
		return nil, fmt.Errorf("BM25 检索参数无效")
	}
	filters := []any{map[string]any{"term": map[string]any{"knowledge_base_id": filter.KnowledgeBaseID}}, map[string]any{"term": map[string]any{"active": true}}}
	if filter.DocumentID != 0 {
		filters = append(filters, map[string]any{"term": map[string]any{"document_id": filter.DocumentID}})
	}
	payload := map[string]any{"size": filter.Limit, "query": map[string]any{"bool": map[string]any{"must": []any{map[string]any{"match": map[string]any{"content": query}}}, "filter": filters}}}
	data, _ := json.Marshal(payload)
	request, err := s.newRequest(ctx, http.MethodPost, "/_search", bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := s.client.Transport.Perform(request)
	if err != nil {
		return nil, fmt.Errorf("执行 OpenSearch BM25 检索失败: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode >= 300 {
		return nil, fmt.Errorf("OpenSearch BM25 检索返回 HTTP %d", response.StatusCode)
	}
	var decoded struct {
		Hits struct {
			Hits []struct {
				Source sourceChunk `json:"_source"`
				Score  float32     `json:"_score"`
			} `json:"hits"`
		} `json:"hits"`
	}
	if err := json.NewDecoder(response.Body).Decode(&decoded); err != nil {
		return nil, fmt.Errorf("解析 OpenSearch 检索响应失败: %w", err)
	}
	results := make([]document.SearchResult, len(decoded.Hits.Hits))
	for i, hit := range decoded.Hits.Hits {
		results[i] = document.SearchResult{Chunk: document.Chunk{ID: hit.Source.ID, DocumentID: hit.Source.DocumentID, KnowledgeBaseID: hit.Source.KnowledgeBaseID, UserID: hit.Source.UserID, IndexVersion: hit.Source.IndexVersion, Content: hit.Source.Content, ContentSHA256: hit.Source.ContentSHA256}, Score: hit.Score}
	}
	return results, nil
}

// newRequest 统一构造带超时的 OpenSearch HTTP 请求。
func (s *OpenSearch) newRequest(ctx context.Context, method, path string, body io.Reader) (*http.Request, error) {
	timeoutCtx, cancel := context.WithTimeout(ctx, s.timeout)
	_ = cancel
	return http.NewRequestWithContext(timeoutCtx, method, s.endpoint+"/"+s.index+path, body)
}
