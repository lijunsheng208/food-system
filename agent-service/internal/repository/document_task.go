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
		Status: model.DocumentIndexTaskPending, ReceivedAt: time.Now(), NextRetryAt: time.Now(),
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

// ClaimIndexTask 原子领取一条到期任务，并回收超过锁时限的处理中任务。
func (r *DocumentTaskRepo) ClaimIndexTask(ctx context.Context, workerID string, lockTimeout time.Duration) (*model.DocumentIndexTask, error) {
	var task model.DocumentIndexTask
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		now := time.Now()
		staleAt := now.Add(-lockTimeout)
		query := tx.Clauses(clause.Locking{Strength: "UPDATE", Options: "SKIP LOCKED"}).
			Where("((status IN (?, ?) AND next_retry_at <= ?) OR (status = ? AND locked_at < ?))", model.DocumentIndexTaskPending, model.DocumentIndexTaskFailed, now, model.DocumentIndexTaskProcessing, staleAt).
			Order("id ASC").Limit(1).Find(&task)
		if query.Error != nil || query.RowsAffected == 0 {
			return query.Error
		}
		updates := map[string]any{"status": model.DocumentIndexTaskProcessing, "attempts": task.Attempts + 1, "locked_by": workerID, "locked_at": now, "last_error": nil}
		if task.StartedAt == nil {
			updates["started_at"] = now
			task.StartedAt = &now
		}
		if err := tx.Model(&model.DocumentIndexTask{}).Where("id = ?", task.ID).Updates(updates).Error; err != nil {
			return err
		}
		task.Status, task.Attempts, task.LockedBy, task.LockedAt = model.DocumentIndexTaskProcessing, task.Attempts+1, &workerID, &now
		return nil
	})
	if err != nil || task.ID == 0 {
		return nil, err
	}
	return &task, nil
}

// MarkIndexTaskCompleted 仅允许持锁 Worker 完成当前任务。
func (r *DocumentTaskRepo) MarkIndexTaskCompleted(ctx context.Context, id uint64, workerID string) error {
	now := time.Now()
	result := r.db.WithContext(ctx).Model(&model.DocumentIndexTask{}).Where("id = ? AND status = ? AND locked_by = ?", id, model.DocumentIndexTaskProcessing, workerID).
		Updates(map[string]any{"status": model.DocumentIndexTaskCompleted, "completed_at": now, "locked_by": nil, "locked_at": nil, "last_error": nil})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected != 1 {
		return fmt.Errorf("文档索引任务执行锁已丢失")
	}
	return nil
}

// MarkIndexTaskFailed 记录失败原因并将任务安排到退避时间后重试。
func (r *DocumentTaskRepo) MarkIndexTaskFailed(ctx context.Context, id uint64, workerID string, nextRetryAt time.Time, cause string) error {
	if len(cause) > 500 {
		cause = cause[:500]
	}
	result := r.db.WithContext(ctx).Model(&model.DocumentIndexTask{}).Where("id = ? AND status = ? AND locked_by = ?", id, model.DocumentIndexTaskProcessing, workerID).
		Updates(map[string]any{"status": model.DocumentIndexTaskFailed, "next_retry_at": nextRetryAt, "last_error": cause, "locked_by": nil, "locked_at": nil})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected != 1 {
		return fmt.Errorf("文档索引任务执行锁已丢失")
	}
	return nil
}
