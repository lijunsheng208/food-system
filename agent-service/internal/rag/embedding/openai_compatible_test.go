package embedding

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

// TestOpenAICompatiblePreservesEmbeddingOrder 验证 Provider 按响应 index 还原输入顺序。
func TestOpenAICompatiblePreservesEmbeddingOrder(t *testing.T) {
	client, err := NewOpenAICompatible(OpenAICompatibleConfig{BaseURL: "https://embedding.example", APIKey: "secret", Model: "test", DimensionsValue: 2, BatchSize: 2, Timeout: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	client.client.Transport = roundTripperFunc(func(request *http.Request) (*http.Response, error) {
		if request.Header.Get("Authorization") != "Bearer secret" {
			t.Error("缺少鉴权头")
		}
		body := `{"data":[{"index":1,"embedding":[2,2]},{"index":0,"embedding":[1,1]}]}`
		return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader(body)), Header: make(http.Header)}, nil
	})
	vectors, err := client.EmbedDocuments(context.Background(), []string{"a", "b"})
	if err != nil {
		t.Fatal(err)
	}
	if vectors[0][0] != 1 || vectors[1][0] != 2 {
		t.Fatalf("向量顺序错误: %+v", vectors)
	}
}

type roundTripperFunc func(*http.Request) (*http.Response, error)

// RoundTrip 让函数适配 http.RoundTripper，避免测试依赖真实监听端口。
func (f roundTripperFunc) RoundTrip(request *http.Request) (*http.Response, error) { return f(request) }
