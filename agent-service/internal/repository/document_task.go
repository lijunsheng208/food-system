package repository

import (
	"context"
	"fmt"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/model"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

// DocumentTaskRepo 负责文档索引任务的幂等持久化。
type DocumentTaskRepo struct{ db *gorm.DB }

// NewDocumentTaskRepo 创建文档索引任务仓储。
func NewDocumentTaskRepo(db *gorm.DB) *DocumentTaskRepo { return &DocumentTaskRepo{db: db} }

// RecordIndexRequest 以文档和索引版本为幂等键记录待解析任务。
func (r *DocumentTaskRepo) RecordIndexRequest(ctx context.Context, eventID string, documentID uint64, indexVersion uint, userID, knowledgeBaseID uint64) (bool, error) {
	task := model.DocumentIndexTask{
		EventID: eventID, DocumentID: documentID, IndexVersion: indexVersion,
		UserID: userID, KnowledgeBaseID: knowledgeBaseID,
		Status: model.DocumentIndexTaskPending, ReceivedAt: time.Now(),
	}
	result := r.db.WithContext(ctx).Clauses(clause.OnConflict{
		Columns:   []clause.Column{{Name: "document_id"}, {Name: "index_version"}},
		DoNothing: true,
	}).Create(&task)
	if result.Error != nil {
		return false, fmt.Errorf("记录文档索引任务失败: %w", result.Error)
	}
	return result.RowsAffected == 1, nil
}
