package repository

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
	"gorm.io/gorm"
)

// DocumentChunk 保存 Agent 关系库中的切片正文和向量引用元数据。
type DocumentChunk struct {
	ID              string    `gorm:"column:id;primaryKey;size:36"`
	DocumentID      uint64    `gorm:"column:document_id"`
	KnowledgeBaseID uint64    `gorm:"column:knowledge_base_id"`
	UserID          uint64    `gorm:"column:user_id"`
	IndexVersion    uint      `gorm:"column:index_version"`
	ChunkIndex      int       `gorm:"column:chunk_index"`
	Content         string    `gorm:"column:content"`
	ContentSHA256   string    `gorm:"column:content_sha256"`
	Metadata        string    `gorm:"column:metadata"`
	CreatedAt       time.Time `gorm:"column:created_at"`
}

// TableName 返回 Agent 文档切片表名。
func (DocumentChunk) TableName() string { return "agent_document_chunk" }

// ChunkRepo 持久化文档版本对应的切片元数据。
type ChunkRepo struct{ db *gorm.DB }

// NewChunkRepo 创建文档切片仓储。
func NewChunkRepo(db *gorm.DB) *ChunkRepo { return &ChunkRepo{db: db} }

// ReplaceVersion 在单个 MySQL 事务中幂等替换指定文档版本的全部切片。
func (r *ChunkRepo) ReplaceVersion(ctx context.Context, documentID uint64, indexVersion uint, chunks []document.Chunk) error {
	if documentID == 0 || indexVersion == 0 || len(chunks) == 0 {
		return fmt.Errorf("待保存切片数据无效")
	}
	rows := make([]DocumentChunk, len(chunks))
	for index, chunk := range chunks {
		if chunk.DocumentID != documentID || chunk.IndexVersion != indexVersion || chunk.ID == "" || chunk.Content == "" {
			return fmt.Errorf("第 %d 个切片数据无效", index)
		}
		metadata, err := json.Marshal(chunk.Metadata)
		if err != nil {
			return fmt.Errorf("编码第 %d 个切片元数据失败: %w", index, err)
		}
		rows[index] = DocumentChunk{ID: chunk.ID, DocumentID: chunk.DocumentID, KnowledgeBaseID: chunk.KnowledgeBaseID, UserID: chunk.UserID, IndexVersion: chunk.IndexVersion, ChunkIndex: chunk.Index, Content: chunk.Content, ContentSHA256: chunk.ContentSHA256, Metadata: string(metadata)}
	}
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("document_id = ? AND index_version = ?", documentID, indexVersion).Delete(&DocumentChunk{}).Error; err != nil {
			return err
		}
		if err := tx.CreateInBatches(rows, 100).Error; err != nil {
			return fmt.Errorf("保存文档切片失败: %w", err)
		}
		return nil
	})
}

// DeleteVersion 删除一次未完成索引写入的关系库切片。
func (r *ChunkRepo) DeleteVersion(ctx context.Context, documentID uint64, indexVersion uint) error {
	return r.db.WithContext(ctx).Where("document_id = ? AND index_version = ?", documentID, indexVersion).Delete(&DocumentChunk{}).Error
}
