package rerank

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"testing"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// TestHTTPRerank 验证客户端发送候选文本并按服务端索引重建顺序。
func TestHTTPRerank(t *testing.T) {
	client, err := NewHTTP(HTTPConfig{BaseURL: "http://reranker.test", APIKey: "secret", Model: "reranker", Timeout: time.Second, TopK: 1})
	if err != nil {
		t.Fatal(err)
	}
	client.client.Transport = roundTripperFunc(func(req *http.Request) (*http.Response, error) {
		if req.URL.Path != "/reranks" || req.Header.Get("Authorization") != "Bearer secret" {
			t.Fatalf("请求路径或认证头错误")
		}
		var body request
		if err := json.NewDecoder(req.Body).Decode(&body); err != nil || len(body.Documents) != 2 || body.Query != "问题" || body.TopN != 1 {
			t.Fatalf("请求体错误: %+v, err=%v", body, err)
		}
		payload, _ := json.Marshal(response{Results: []struct {
			Index          int     `json:"index"`
			RelevanceScore float32 `json:"relevance_score"`
		}{{Index: 1, RelevanceScore: 0.9}, {Index: 0, RelevanceScore: 0.2}}})
		return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(bytes.NewReader(payload)), Header: make(http.Header), Request: req}, nil
	})
	results, err := client.Rerank(context.Background(), "问题", []document.SearchResult{{Chunk: document.Chunk{ID: "a", Content: "甲"}}, {Chunk: document.Chunk{ID: "b", Content: "乙"}}})
	if err != nil || len(results) != 2 || results[0].ID != "b" || results[0].Score != 0.9 {
		t.Fatalf("重排结果错误: %+v, err=%v", results, err)
	}
}

type roundTripperFunc func(*http.Request) (*http.Response, error)

// RoundTrip 将测试请求交给内存中的响应函数，避免依赖本地监听端口。
func (f roundTripperFunc) RoundTrip(req *http.Request) (*http.Response, error) { return f(req) }
