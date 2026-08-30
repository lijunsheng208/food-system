package vectorstore

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
	"github.com/pgvector/pgvector-go"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

// PGVector 使用 PostgreSQL pgvector 保存和检索文档切片。
type PGVector struct {
	db         *gorm.DB
	dimensions int
}

type vectorRow struct {
	ID              string          `gorm:"column:id;primaryKey;type:uuid"`
	DocumentID      uint64          `gorm:"column:document_id"`
	KnowledgeBaseID uint64          `gorm:"column:knowledge_base_id"`
	UserID          uint64          `gorm:"column:user_id"`
	IndexVersion    uint            `gorm:"column:index_version"`
	ChunkIndex      int             `gorm:"column:chunk_index"`
	Content         string          `gorm:"column:content"`
	ContentSHA256   string          `gorm:"column:content_sha256"`
	Metadata        []byte          `gorm:"column:metadata;type:jsonb"`
	Embedding       pgvector.Vector `gorm:"column:embedding;type:vector"`
	Active          bool            `gorm:"column:active"`
}

// TableName 返回 pgvector 切片表名。
func (vectorRow) TableName() string { return "agent_document_vectors" }

// NewPGVector 校验 pgvector 可用性并创建固定维度的向量表。
func NewPGVector(db *gorm.DB, dimensions int) (*PGVector, error) {
	if db == nil || dimensions <= 0 || dimensions > 2000 {
		return nil, fmt.Errorf("pgvector 配置无效")
	}
	if err := db.Exec("CREATE EXTENSION IF NOT EXISTS vector").Error; err != nil {
		return nil, fmt.Errorf("启用 pgvector 扩展失败: %w", err)
	}
	createSQL := fmt.Sprintf(`CREATE TABLE IF NOT EXISTS agent_document_vectors (
id uuid PRIMARY KEY, document_id bigint NOT NULL, knowledge_base_id bigint NOT NULL, user_id bigint NOT NULL,
index_version integer NOT NULL, chunk_index integer NOT NULL, content text NOT NULL, content_sha256 char(64) NOT NULL,
metadata jsonb NOT NULL DEFAULT '{}'::jsonb, embedding vector(%d) NOT NULL, active boolean NOT NULL DEFAULT false,
created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(document_id, index_version, chunk_index))`, dimensions)
	if err := db.Exec(createSQL).Error; err != nil {
		return nil, fmt.Errorf("创建 pgvector 文档表失败: %w", err)
	}
	if err := db.Exec("CREATE INDEX IF NOT EXISTS idx_agent_vectors_scope ON agent_document_vectors (knowledge_base_id, active)").Error; err != nil {
		return nil, fmt.Errorf("创建 pgvector 范围索引失败: %w", err)
	}
	if err := db.Exec("CREATE INDEX IF NOT EXISTS idx_agent_vectors_embedding_hnsw ON agent_document_vectors USING hnsw (embedding vector_cosine_ops)").Error; err != nil {
		return nil, fmt.Errorf("创建 pgvector HNSW 索引失败: %w", err)
	}
	return &PGVector{db: db, dimensions: dimensions}, nil
}

// ReplaceDocumentVersion 原子写入新版本并将同一文档旧版本停用。
func (s *PGVector) ReplaceDocumentVersion(ctx context.Context, documentID uint64, indexVersion uint, chunks []document.EmbeddedChunk) error {
	if documentID == 0 || indexVersion == 0 || len(chunks) == 0 {
		return fmt.Errorf("待写入向量数据无效")
	}
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		rows := make([]vectorRow, len(chunks))
		for index, chunk := range chunks {
			if chunk.DocumentID != documentID || chunk.IndexVersion != indexVersion || len(chunk.Embedding) != s.dimensions {
				return fmt.Errorf("切片 %d 的文档版本或向量维度无效", index)
			}
			metadata, err := json.Marshal(chunk.Metadata)
			if err != nil {
				return fmt.Errorf("编码切片元数据失败: %w", err)
			}
			rows[index] = vectorRow{ID: chunk.ID, DocumentID: chunk.DocumentID, KnowledgeBaseID: chunk.KnowledgeBaseID, UserID: chunk.UserID, IndexVersion: chunk.IndexVersion, ChunkIndex: chunk.Index, Content: chunk.Content, ContentSHA256: chunk.ContentSHA256, Metadata: metadata, Embedding: pgvector.NewVector(chunk.Embedding), Active: true}
		}
		if err := tx.Where("document_id = ? AND index_version = ?", documentID, indexVersion).Delete(&vectorRow{}).Error; err != nil {
			return err
		}
		if err := tx.CreateInBatches(rows, 100).Error; err != nil {
			return fmt.Errorf("写入 pgvector 失败: %w", err)
		}
		if err := tx.Model(&vectorRow{}).Where("document_id = ? AND index_version <> ? AND active = true", documentID, indexVersion).Update("active", false).Error; err != nil {
			return fmt.Errorf("停用旧向量版本失败: %w", err)
		}
		return nil
	})
}

// DeleteDocumentVersion 删除一次未完成或已过期的索引版本。
func (s *PGVector) DeleteDocumentVersion(ctx context.Context, documentID uint64, indexVersion uint) error {
	return s.db.WithContext(ctx).Where("document_id = ? AND index_version = ?", documentID, indexVersion).Delete(&vectorRow{}).Error
}

// Search 在指定知识库的活动版本中执行余弦相似度检索。
func (s *PGVector) Search(ctx context.Context, query []float32, filter document.SearchFilter) ([]document.SearchResult, error) {
	if len(query) != s.dimensions || filter.KnowledgeBaseID == 0 || filter.Limit <= 0 || filter.Limit > 100 {
		return nil, fmt.Errorf("向量检索参数无效")
	}
	type searchRow struct {
		vectorRow
		Score float32 `gorm:"column:score"`
	}
	statement := s.db.WithContext(ctx).Table("agent_document_vectors").Select("*, 1 - (embedding <=> ?) AS score", pgvector.NewVector(query)).Where("knowledge_base_id = ? AND active = true", filter.KnowledgeBaseID)
	if filter.DocumentID != 0 {
		statement = statement.Where("document_id = ?", filter.DocumentID)
	}
	var rows []searchRow
	if err := statement.Order(clause.Expr{SQL: "embedding <=> ?", Vars: []any{pgvector.NewVector(query)}}).Limit(filter.Limit).Scan(&rows).Error; err != nil {
		return nil, fmt.Errorf("执行 pgvector 检索失败: %w", err)
	}
	results := make([]document.SearchResult, len(rows))
	for index, row := range rows {
		var metadata map[string]any
		if len(row.Metadata) == 0 || strings.TrimSpace(string(row.Metadata)) == "null" || strings.TrimSpace(string(row.Metadata)) == "" {
			metadata = map[string]any{}
		} else if err := json.Unmarshal(row.Metadata, &metadata); err != nil {
			return nil, fmt.Errorf("解析向量元数据失败: document_id=%d chunk_id=%q metadata_len=%d: %w", row.DocumentID, row.ID, len(row.Metadata), err)
		}
		results[index] = document.SearchResult{Chunk: document.Chunk{ID: row.ID, DocumentID: row.DocumentID, KnowledgeBaseID: row.KnowledgeBaseID, UserID: row.UserID, IndexVersion: row.IndexVersion, Index: row.ChunkIndex, Content: row.Content, ContentSHA256: row.ContentSHA256, Metadata: metadata}, Score: row.Score}
	}
	return results, nil
}
