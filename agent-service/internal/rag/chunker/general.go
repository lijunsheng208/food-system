package chunker

import (
	"context"
	"crypto/sha256"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// GeneralConfig 描述按字符切片的大小和重叠区间。
type GeneralConfig struct {
	Size    int
	Overlap int
}

// General 优先按段落和句子边界切分文本。
type General struct{ config GeneralConfig }

// NewGeneral 创建通用切片器。
func NewGeneral(config GeneralConfig) (*General, error) {
	if config.Size <= 0 || config.Overlap < 0 || config.Overlap >= config.Size {
		return nil, fmt.Errorf("通用切片配置无效")
	}
	return &General{config: config}, nil
}

// Chunk 参考 LightningRAG 通用策略生成带稳定业务元数据的切片。
func (c *General) Chunk(_ context.Context, source document.SourceDocument, parsed *document.ParsedDocument) ([]document.Chunk, error) {
	if parsed == nil {
		return nil, fmt.Errorf("待切片文档不能为空")
	}
	texts := splitText(parsed.Text, c.config.Size, c.config.Overlap)
	chunks := make([]document.Chunk, 0, len(texts))
	for index, text := range texts {
		digest := fmt.Sprintf("%x", sha256.Sum256([]byte(text)))
		metadata := map[string]any{"filename": source.Filename, "content_type": source.ContentType, "chunk_index": index}
		for key, value := range parsed.Metadata {
			metadata[key] = value
		}
		chunks = append(chunks, document.Chunk{ID: uuid.NewString(), DocumentID: source.DocumentID, KnowledgeBaseID: source.KnowledgeBaseID, UserID: source.UserID, IndexVersion: source.IndexVersion, Index: index, Content: text, ContentSHA256: digest, Metadata: metadata})
	}
	return chunks, nil
}

// splitText 按段落和中英文句末标记切分，并为相邻切片保留重叠文本。
func splitText(text string, size, overlap int) []string {
	text = strings.TrimSpace(text)
	if text == "" {
		return nil
	}
	segments := splitSegments(text)
	var result []string
	var current []rune
	flush := func() {
		value := strings.TrimSpace(string(current))
		if value != "" {
			result = append(result, value)
		}
		if overlap > 0 && len(current) > overlap {
			current = append([]rune(nil), current[len(current)-overlap:]...)
		} else {
			current = nil
		}
	}
	for _, segment := range segments {
		runes := []rune(strings.TrimSpace(segment))
		for len(runes) > 0 {
			remaining := size - len(current)
			if remaining <= 0 {
				flush()
				remaining = size - len(current)
			}
			addSeparator := len(current) > 0 && remaining > 1
			if addSeparator {
				remaining--
			}
			take := len(runes)
			if take > remaining {
				take = remaining
			}
			if addSeparator && take > 0 {
				current = append(current, '\n')
			}
			current = append(current, runes[:take]...)
			runes = runes[take:]
			if len(current) >= size {
				flush()
			}
		}
	}
	if value := strings.TrimSpace(string(current)); value != "" {
		result = append(result, value)
	}
	return result
}

// splitSegments 将段落进一步按常见句末字符切开。
func splitSegments(text string) []string {
	var segments []string
	var current strings.Builder
	for _, value := range text {
		current.WriteRune(value)
		if strings.ContainsRune("。！？；.!?\n", value) {
			if segment := strings.TrimSpace(current.String()); segment != "" {
				segments = append(segments, segment)
			}
			current.Reset()
		}
	}
	if segment := strings.TrimSpace(current.String()); segment != "" {
		segments = append(segments, segment)
	}
	return segments
}
