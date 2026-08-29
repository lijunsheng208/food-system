package indexer

import (
	"bytes"
	"context"
	"crypto/sha256"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/model"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/chunker"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/embedding"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/parser"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/vectorstore"
	"github.com/lijunsheng/familyos/agent-service/internal/service"
)

// DocumentIndexerConfig 描述下载超时和文件大小上限。
type DocumentIndexerConfig struct {
	DownloadTimeout time.Duration
	MaxFileSize     int64
}

// ChunkRepository 提供索引器所需的关系库切片版本写入和补偿删除。
type ChunkRepository interface {
	ReplaceVersion(ctx context.Context, documentID uint64, indexVersion uint, chunks []document.Chunk) error
	DeleteVersion(ctx context.Context, documentID uint64, indexVersion uint) error
}

// DocumentIndexer 执行下载校验、解析、切片、向量化和版本写入。
type DocumentIndexer struct {
	parsers     *parser.Registry
	chunker     chunker.Chunker
	embedder    embedding.Embedder
	vectors     vectorstore.Store
	chunks      ChunkRepository
	client      *http.Client
	maxFileSize int64
}

// NewDocumentIndexer 创建完整文档索引处理器。
func NewDocumentIndexer(parsers *parser.Registry, chunker chunker.Chunker, embedder embedding.Embedder, vectors vectorstore.Store, chunks ChunkRepository, config DocumentIndexerConfig) (*DocumentIndexer, error) {
	if parsers == nil || chunker == nil || embedder == nil || vectors == nil || chunks == nil || config.DownloadTimeout <= 0 || config.MaxFileSize <= 0 {
		return nil, fmt.Errorf("文档索引器配置无效")
	}
	return &DocumentIndexer{parsers: parsers, chunker: chunker, embedder: embedder, vectors: vectors, chunks: chunks, client: &http.Client{Timeout: config.DownloadTimeout}, maxFileSize: config.MaxFileSize}, nil
}

// ProcessDocument 实现 Worker 处理器，只有关系库和 pgvector 都写入成功才返回成功。
func (i *DocumentIndexer) ProcessDocument(ctx context.Context, task *model.DocumentIndexTask, ticket *service.DocumentDownloadTicket) error {
	if task == nil || ticket == nil || task.DocumentID == 0 || task.IndexVersion == 0 {
		return fmt.Errorf("文档索引任务无效")
	}
	content, err := i.download(ctx, ticket)
	if err != nil {
		return err
	}
	source := document.SourceDocument{DocumentID: task.DocumentID, KnowledgeBaseID: task.KnowledgeBaseID, UserID: task.UserID, IndexVersion: task.IndexVersion, Filename: ticket.OriginalFilename, Extension: ticket.FileExtension, ContentType: ticket.ContentType, Content: content}
	documentParser, err := i.parsers.Resolve(source.Extension, source.Filename)
	if err != nil {
		return err
	}
	parsed, err := documentParser.Parse(ctx, bytes.NewReader(content), source)
	if err != nil {
		return fmt.Errorf("解析文档失败: %w", err)
	}
	chunks, err := i.chunker.Chunk(ctx, source, parsed)
	if err != nil {
		return fmt.Errorf("切分文档失败: %w", err)
	}
	if len(chunks) == 0 {
		return fmt.Errorf("文档解析后没有可索引内容")
	}
	texts := make([]string, len(chunks))
	for index := range chunks {
		texts[index] = chunks[index].Content
	}
	vectors, err := i.embedder.EmbedDocuments(ctx, texts)
	if err != nil {
		return fmt.Errorf("生成文档向量失败: %w", err)
	}
	if len(vectors) != len(chunks) {
		return fmt.Errorf("文档向量数量不匹配")
	}
	embedded := make([]document.EmbeddedChunk, len(chunks))
	for index := range chunks {
		embedded[index] = document.EmbeddedChunk{Chunk: chunks[index], Embedding: vectors[index]}
	}
	if err := i.chunks.ReplaceVersion(ctx, task.DocumentID, task.IndexVersion, chunks); err != nil {
		return err
	}
	if err := i.vectors.ReplaceDocumentVersion(ctx, task.DocumentID, task.IndexVersion, embedded); err != nil {
		if cleanupErr := i.chunks.DeleteVersion(ctx, task.DocumentID, task.IndexVersion); cleanupErr != nil {
			return fmt.Errorf("写入向量失败: %v; 清理关系库切片失败: %w", err, cleanupErr)
		}
		return err
	}
	return nil
}

// download 使用短期签名地址下载文件，并校验协议、大小和可选 SHA256。
func (i *DocumentIndexer) download(ctx context.Context, ticket *service.DocumentDownloadTicket) ([]byte, error) {
	parsedURL, err := url.Parse(ticket.DownloadURL)
	if err != nil || (parsedURL.Scheme != "http" && parsedURL.Scheme != "https") || parsedURL.Host == "" {
		return nil, fmt.Errorf("文档下载地址无效")
	}
	if ticket.FileSize <= 0 || ticket.FileSize > i.maxFileSize {
		return nil, fmt.Errorf("文档大小超出索引限制")
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, ticket.DownloadURL, nil)
	if err != nil {
		return nil, fmt.Errorf("创建文档下载请求失败: %w", err)
	}
	response, err := i.client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("下载文档失败: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, fmt.Errorf("下载文档返回 HTTP %d", response.StatusCode)
	}
	content, err := io.ReadAll(io.LimitReader(response.Body, i.maxFileSize+1))
	if err != nil {
		return nil, fmt.Errorf("读取下载文档失败: %w", err)
	}
	if int64(len(content)) > i.maxFileSize || int64(len(content)) != ticket.FileSize {
		return nil, fmt.Errorf("下载文档大小不匹配: expected=%d actual=%d", ticket.FileSize, len(content))
	}
	if ticket.SHA256 != "" {
		actual := fmt.Sprintf("%x", sha256.Sum256(content))
		if !strings.EqualFold(actual, ticket.SHA256) {
			return nil, fmt.Errorf("下载文档 SHA256 不匹配")
		}
	}
	return content, nil
}
