package chunker

import (
	"context"
	"testing"
	"unicode/utf8"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// TestGeneralChunkHonorsSize 验证中英文文本切片不会超过配置字符数。
func TestGeneralChunkHonorsSize(t *testing.T) {
	value, err := NewGeneral(GeneralConfig{Size: 12, Overlap: 3})
	if err != nil {
		t.Fatal(err)
	}
	chunks, err := value.Chunk(context.Background(), document.SourceDocument{DocumentID: 1, KnowledgeBaseID: 2, UserID: 3, IndexVersion: 1, Filename: "a.md"}, &document.ParsedDocument{Text: "第一句话。第二句话很长。Third sentence."})
	if err != nil {
		t.Fatal(err)
	}
	if len(chunks) < 2 {
		t.Fatalf("切片数量 = %d", len(chunks))
	}
	for _, chunk := range chunks {
		if utf8.RuneCountInString(chunk.Content) > 12 {
			t.Fatalf("切片超过限制: %q", chunk.Content)
		}
		if chunk.ContentSHA256 == "" || chunk.ID == "" {
			t.Fatalf("切片元数据不完整: %+v", chunk)
		}
	}
}
