package indexer

import (
	"context"
	"crypto/sha256"
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/model"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/chunker"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/parser"
	"github.com/lijunsheng/familyos/agent-service/internal/service"
)

type embedderStub struct{}

// EmbedDocuments 为每段测试文本返回固定维度向量。
func (embedderStub) EmbedDocuments(_ context.Context, texts []string) ([][]float32, error) {
	result := make([][]float32, len(texts))
	for index := range result {
		result[index] = []float32{1, 0}
	}
	return result, nil
}

// EmbedQuery 返回固定测试查询向量。
func (embedderStub) EmbedQuery(context.Context, string) ([]float32, error) {
	return []float32{1, 0}, nil
}

// Dimensions 返回测试向量维度。
func (embedderStub) Dimensions() int { return 2 }

type vectorStoreStub struct{ replaced []document.EmbeddedChunk }

// ReplaceDocumentVersion 记录测试索引器写入的向量切片。
func (s *vectorStoreStub) ReplaceDocumentVersion(_ context.Context, _ uint64, _ uint, chunks []document.EmbeddedChunk) error {
	s.replaced = chunks
	return nil
}

// DeleteDocumentVersion 模拟删除测试向量版本。
func (s *vectorStoreStub) DeleteDocumentVersion(context.Context, uint64, uint) error { return nil }

// Search 不参与索引器测试。
func (s *vectorStoreStub) Search(context.Context, []float32, document.SearchFilter) ([]document.SearchResult, error) {
	return nil, nil
}

type chunkRepoStub struct {
	replaced []document.Chunk
	deleted  bool
}

// ReplaceVersion 记录关系库切片写入。
func (r *chunkRepoStub) ReplaceVersion(_ context.Context, _ uint64, _ uint, chunks []document.Chunk) error {
	r.replaced = chunks
	return nil
}

// DeleteVersion 记录失败补偿删除。
func (r *chunkRepoStub) DeleteVersion(context.Context, uint64, uint) error {
	r.deleted = true
	return nil
}

type roundTripperFunc func(*http.Request) (*http.Response, error)

// RoundTrip 让函数适配 http.RoundTripper。
func (f roundTripperFunc) RoundTrip(request *http.Request) (*http.Response, error) { return f(request) }

// TestDocumentIndexerProcessesDownloadedText 验证下载校验到双存储写入的完整索引流程。
func TestDocumentIndexerProcessesDownloadedText(t *testing.T) {
	content := []byte("第一段内容。第二段内容。")
	digest := fmt.Sprintf("%x", sha256.Sum256(content))
	documentChunker, err := chunker.NewGeneral(chunker.GeneralConfig{Size: 8, Overlap: 2})
	if err != nil {
		t.Fatal(err)
	}
	vectors, chunks := &vectorStoreStub{}, &chunkRepoStub{}
	value, err := NewDocumentIndexer(parser.NewRegistry(), documentChunker, embedderStub{}, vectors, chunks, DocumentIndexerConfig{DownloadTimeout: time.Second, MaxFileSize: 1024})
	if err != nil {
		t.Fatal(err)
	}
	value.client.Transport = roundTripperFunc(func(*http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: http.StatusOK, Body: io.NopCloser(strings.NewReader(string(content))), Header: make(http.Header)}, nil
	})
	task := &model.DocumentIndexTask{DocumentID: 7, KnowledgeBaseID: 8, UserID: 9, IndexVersion: 1}
	ticket := &service.DocumentDownloadTicket{DownloadURL: "https://oss.example/document", OriginalFilename: "note.txt", FileExtension: ".txt", ContentType: "text/plain", FileSize: int64(len(content)), SHA256: digest}
	if err := value.ProcessDocument(context.Background(), task, ticket); err != nil {
		t.Fatalf("索引失败: %v", err)
	}
	if len(chunks.replaced) == 0 || len(vectors.replaced) != len(chunks.replaced) || chunks.deleted {
		t.Fatalf("写入结果不一致: chunks=%d vectors=%d deleted=%v", len(chunks.replaced), len(vectors.replaced), chunks.deleted)
	}
}
