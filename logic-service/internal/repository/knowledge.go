package repository

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
	"time"
)

const ulidEncoding = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

// documentIndexEvent 描述发送给 Agent 的文档索引消息载荷。
type documentIndexEvent struct {
	SchemaVersion   int    `json:"schema_version"`
	EventID         string `json:"event_id"`
	EventType       string `json:"event_type"`
	DocumentID      uint64 `json:"document_id"`
	UserID          uint64 `json:"user_id"`
	KnowledgeBaseID uint64 `json:"knowledge_base_id"`
	IndexVersion    uint   `json:"index_version"`
	OccurredAt      string `json:"occurred_at"`
}

// documentDeleteEvent 描述发送给 Agent 的文档索引删除消息载荷。
type documentDeleteEvent struct {
	SchemaVersion     int    `json:"schema_version"`
	EventID           string `json:"event_id"`
	EventType         string `json:"event_type"`
	DocumentID        uint64 `json:"document_id"`
	UserID            uint64 `json:"user_id"`
	KnowledgeBaseID   uint64 `json:"knowledge_base_id"`
	DeleteAllVersions bool   `json:"delete_all_versions"`
	OccurredAt        string `json:"occurred_at"`
}

// KnowledgeRepo 处理上传票据涉及的知识库持久化操作。
type KnowledgeRepo struct{ db *gorm.DB }

// NewKnowledgeRepo 创建知识库仓储。
func NewKnowledgeRepo(db *gorm.DB) *KnowledgeRepo { return &KnowledgeRepo{db: db} }

// GetBase 查询知识库。
func (r *KnowledgeRepo) GetBase(ctx context.Context, id uint64) (*model.KnowledgeBase, error) {
	var value model.KnowledgeBase
	if err := r.db.WithContext(ctx).First(&value, id).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return nil, nil
		}
		return nil, err
	}
	return &value, nil
}

// GetOrCreatePersonalBase 幂等获取用户默认个人知识库，避免客户端依赖固定 ID。
func (r *KnowledgeRepo) GetOrCreatePersonalBase(ctx context.Context, userID uint64) (*model.KnowledgeBase, error) {
	var base model.KnowledgeBase
	err := r.db.WithContext(ctx).Where("scope_type = 1 AND owner_user_id = ? AND is_default = 1 AND status = 1", userID).First(&base).Error
	if err == nil {
		return &base, nil
	}
	if err != gorm.ErrRecordNotFound {
		return nil, err
	}
	base = model.KnowledgeBase{ScopeType: model.KnowledgeScopePersonal, OwnerUserID: &userID, Name: "我的知识库", Status: 1, IsDefault: 1, CreatedBy: userID}
	if err := r.db.WithContext(ctx).Create(&base).Error; err != nil {
		if err := r.db.WithContext(ctx).Where("scope_type = 1 AND owner_user_id = ? AND is_default = 1 AND status = 1", userID).First(&base).Error; err != nil {
			return nil, err
		}
	}
	return &base, nil
}

// GetDocument 查询文档。
func (r *KnowledgeRepo) GetDocument(ctx context.Context, id uint64) (*model.KnowledgeDocument, error) {
	var value model.KnowledgeDocument
	if err := r.db.WithContext(ctx).First(&value, id).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return nil, nil
		}
		return nil, err
	}
	return &value, nil
}

// CompleteDocumentIndex 仅在版本仍匹配时激活 Agent 已完整写入的索引版本。
func (r *KnowledgeRepo) CompleteDocumentIndex(ctx context.Context, documentID uint64, indexVersion uint) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var document model.KnowledgeDocument
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&document, documentID).Error; err != nil {
			return err
		}
		if document.IndexVersion != indexVersion {
			return ErrDocumentIndexVersionChanged
		}
		// Agent 回报成功但响应丢失时允许幂等重试，避免重复执行完整索引流程。
		if document.Status == model.DocumentCompleted && document.ActiveIndexVersion == indexVersion {
			return nil
		}
		if document.Status != model.DocumentPending && document.Status != model.DocumentProcessing && document.Status != model.DocumentCompleted {
			return ErrDocumentIndexVersionChanged
		}
		return tx.Model(&model.KnowledgeDocument{}).Where("id = ?", documentID).Updates(map[string]any{"status": model.DocumentCompleted, "active_index_version": indexVersion}).Error
	})
}

// ErrDocumentIndexVersionChanged 表示 Agent 完成的版本已不再是 Logic 当前目标版本。
var ErrDocumentIndexVersionChanged = errors.New("文档索引版本已经变化")

// GetDocumentWithSession 锁定查询文档及其上传会话，供确认和清理使用。
func (r *KnowledgeRepo) GetDocumentWithSession(ctx context.Context, id uint64) (*model.KnowledgeDocument, *model.KnowledgeUploadSession, error) {
	var document model.KnowledgeDocument
	if err := r.db.WithContext(ctx).First(&document, id).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return nil, nil, nil
		}
		return nil, nil, err
	}
	var session model.KnowledgeUploadSession
	if err := r.db.WithContext(ctx).Where("document_id = ?", id).First(&session).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return &document, nil, nil
		}
		return nil, nil, err
	}
	return &document, &session, nil
}

// CreateUpload 创建文档和上传会话，保持二者原子可见。
func (r *KnowledgeRepo) CreateUpload(ctx context.Context, document *model.KnowledgeDocument, session *model.KnowledgeUploadSession) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(document).Error; err != nil {
			return err
		}
		session.DocumentID = document.ID
		return tx.Create(session).Error
	})
}

// CompleteUpload 在单个事务中确认会话、更新文档并写入索引事件。
func (r *KnowledgeRepo) CompleteUpload(ctx context.Context, documentID uint64, size uint64, etag string, sha256 *string) (*model.KnowledgeDocument, error) {
	var document model.KnowledgeDocument
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&document, documentID).Error; err != nil {
			return err
		}
		if document.Status != model.DocumentUploading {
			return nil
		}
		var session model.KnowledgeUploadSession
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Where("document_id = ?", documentID).First(&session).Error; err != nil {
			return err
		}
		if session.Status != model.UploadSessionPending || !session.ExpiresAt.After(time.Now()) {
			return fmt.Errorf("上传会话已过期")
		}
		now := time.Now()
		sessionResult := tx.Model(&model.KnowledgeUploadSession{}).Where("id = ? AND status = ?", session.ID, model.UploadSessionPending).Updates(map[string]any{"status": model.UploadSessionConfirmed, "confirmed_at": now})
		if sessionResult.Error != nil {
			return sessionResult.Error
		}
		if sessionResult.RowsAffected != 1 {
			return fmt.Errorf("上传会话状态已变化")
		}
		result := tx.Model(&model.KnowledgeDocument{}).Where("id = ? AND status = ?", documentID, model.DocumentUploading).Updates(map[string]any{"status": model.DocumentPending, "file_size": size, "file_sha256": sha256, "oss_etag": etag, "uploaded_at": now})
		if result.Error != nil {
			return result.Error
		}
		if result.RowsAffected != 1 {
			return fmt.Errorf("文档状态已变化")
		}
		eventID, err := newULID(now)
		if err != nil {
			return err
		}
		payload, err := json.Marshal(documentIndexEvent{
			SchemaVersion: 1, EventID: eventID, EventType: "document.index.requested",
			DocumentID: documentID, UserID: document.CreatedBy, KnowledgeBaseID: document.KnowledgeBaseID,
			IndexVersion: document.IndexVersion, OccurredAt: now.Format(time.RFC3339Nano),
		})
		if err != nil {
			return fmt.Errorf("编码文档索引事件失败: %w", err)
		}
		if err := tx.Create(&model.IntegrationOutbox{EventID: eventID, DedupKey: fmt.Sprintf("document:%d:index:%d", documentID, document.IndexVersion), AggregateType: "knowledge_document", AggregateID: documentID, EventType: "document.index.requested.v1", Topic: "familyos-rag-document", Tag: "INDEX", Payload: string(payload), Status: model.OutboxPending, Attempts: 0, NextRetryAt: now}).Error; err != nil {
			return err
		}
		// GORM 的 Updates 不会回写 struct；这里保持 RPC 响应与已提交状态一致。
		document.Status = model.DocumentPending
		document.FileSize = &size
		document.FileSHA256 = sha256
		document.OSSETag = &etag
		document.UploadedAt = &now
		return nil
	})
	if err != nil {
		return nil, err
	}
	return &document, nil
}

// RequestDocumentDeletion 将文档置为删除中，并与 DELETE 事件在同一事务内写入 Outbox。
func (r *KnowledgeRepo) RequestDocumentDeletion(ctx context.Context, documentID uint64) (*model.KnowledgeDocument, error) {
	var document model.KnowledgeDocument
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&document, documentID).Error; err != nil {
			return err
		}
		if document.Status == model.DocumentDeleting || document.Status == model.DocumentDeleted {
			return nil
		}
		result := tx.Model(&model.KnowledgeDocument{}).
			Where("id = ? AND status NOT IN (?, ?)", documentID, model.DocumentDeleting, model.DocumentDeleted).
			Update("status", model.DocumentDeleting)
		if result.Error != nil {
			return result.Error
		}
		if result.RowsAffected != 1 {
			return fmt.Errorf("文档状态已变化")
		}
		now := time.Now()
		eventID, err := newULID(now)
		if err != nil {
			return err
		}
		payload, err := json.Marshal(documentDeleteEvent{
			SchemaVersion: 1, EventID: eventID, EventType: "document.delete.requested",
			DocumentID: document.ID, UserID: document.CreatedBy, KnowledgeBaseID: document.KnowledgeBaseID,
			DeleteAllVersions: true, OccurredAt: now.Format(time.RFC3339Nano),
		})
		if err != nil {
			return fmt.Errorf("编码文档删除事件失败: %w", err)
		}
		return tx.Create(&model.IntegrationOutbox{
			EventID: eventID, DedupKey: fmt.Sprintf("document:%d:delete:all", documentID),
			AggregateType: "knowledge_document", AggregateID: documentID,
			EventType: "document.delete.requested.v1", Topic: "familyos-rag-document", Tag: "DELETE",
			Payload: string(payload), Status: model.OutboxPending, Attempts: 0, NextRetryAt: now,
		}).Error
	})
	if err != nil {
		return nil, err
	}
	return &document, nil
}

// ExpireUploadSessions 将过期未确认会话原子标记为过期，并将文档转入删除中。
func (r *KnowledgeRepo) ExpireUploadSessions(ctx context.Context, now time.Time) ([]model.KnowledgeDocument, error) {
	var documents []model.KnowledgeDocument
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var sessions []model.KnowledgeUploadSession
		if err := tx.Where("status = ? AND expires_at <= ?", model.UploadSessionPending, now).Find(&sessions).Error; err != nil {
			return err
		}
		for _, session := range sessions {
			if err := tx.Model(&model.KnowledgeUploadSession{}).Where("id = ? AND status = 0", session.ID).Updates(map[string]any{"status": model.UploadSessionExpired}).Error; err != nil {
				return err
			}
			if err := tx.Model(&model.KnowledgeDocument{}).Where("id = ? AND status = 0", session.DocumentID).Updates(map[string]any{"status": model.DocumentDeleting}).Error; err != nil {
				return err
			}
			var document model.KnowledgeDocument
			if err := tx.First(&document, session.DocumentID).Error; err == nil {
				documents = append(documents, document)
			}
		}
		return nil
	})
	return documents, err
}

// newULID 生成按毫秒时间排序的 26 位 Crockford Base32 ULID，用作跨服务事件 ID。
func newULID(now time.Time) (string, error) {
	var bytes [16]byte
	milliseconds := uint64(now.UnixMilli())
	bytes[0] = byte(milliseconds >> 40)
	bytes[1] = byte(milliseconds >> 32)
	bytes[2] = byte(milliseconds >> 24)
	bytes[3] = byte(milliseconds >> 16)
	bytes[4] = byte(milliseconds >> 8)
	bytes[5] = byte(milliseconds)
	if _, err := rand.Read(bytes[6:]); err != nil {
		return "", fmt.Errorf("生成 Outbox 事件 ID 失败: %w", err)
	}

	encoded := make([]byte, 26)
	var buffer uint32
	// ULID 的 128 位数据以两个前导 0 补齐为 130 位，恰好编码为 26 个 Base32 字符。
	bits := 2
	position := 0
	for _, value := range bytes {
		buffer = buffer<<8 | uint32(value)
		bits += 8
		for bits >= 5 {
			bits -= 5
			encoded[position] = ulidEncoding[(buffer>>bits)&31]
			position++
		}
	}
	if bits > 0 {
		encoded[position] = ulidEncoding[(buffer<<(5-bits))&31]
	}
	return string(encoded), nil
}

// ClaimOutboxEvent 原子抢占一条到期事件，发送网络请求不应持有数据库事务。
func (r *KnowledgeRepo) ClaimOutboxEvent(ctx context.Context, workerID string, lockTimeout time.Duration) (*model.IntegrationOutbox, error) {
	var event model.IntegrationOutbox
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		now := time.Now()
		staleAt := now.Add(-lockTimeout)
		query := tx.Clauses(clause.Locking{Strength: "UPDATE", Options: "SKIP LOCKED"}).
			Where("((status IN (?, ?) AND next_retry_at <= ?) OR (status = ? AND locked_at < ?))",
				model.OutboxPending, model.OutboxFailed, now, model.OutboxSending, staleAt).
			Order("id ASC").Limit(1).Find(&event)
		if query.Error != nil {
			return query.Error
		}
		if query.RowsAffected == 0 {
			return nil
		}
		result := tx.Model(&model.IntegrationOutbox{}).
			Where("id = ?", event.ID).
			Updates(map[string]any{
				"status": model.OutboxSending, "attempts": event.Attempts + 1,
				"locked_by": workerID, "locked_at": now, "last_error": nil,
			})
		if result.Error != nil {
			return result.Error
		}
		event.Status, event.Attempts = model.OutboxSending, event.Attempts+1
		event.LockedBy, event.LockedAt = &workerID, &now
		return nil
	})
	if err != nil || event.ID == 0 {
		return nil, err
	}
	return &event, nil
}

// MarkOutboxSent 仅允许持有锁的 Publisher 将事件标记为已发送。
func (r *KnowledgeRepo) MarkOutboxSent(ctx context.Context, id uint64, workerID string) error {
	now := time.Now()
	result := r.db.WithContext(ctx).Model(&model.IntegrationOutbox{}).
		Where("id = ? AND status = ? AND locked_by = ?", id, model.OutboxSending, workerID).
		Updates(map[string]any{"status": model.OutboxSent, "published_at": now, "locked_by": nil, "locked_at": nil, "last_error": nil})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected != 1 {
		return fmt.Errorf("Outbox 事件发送锁已丢失")
	}
	return nil
}

// MarkOutboxFailed 记录发送失败并按退避时间再次调度事件。
func (r *KnowledgeRepo) MarkOutboxFailed(ctx context.Context, id uint64, workerID string, nextRetryAt time.Time, cause string) error {
	if len(cause) > 500 {
		cause = cause[:500]
	}
	result := r.db.WithContext(ctx).Model(&model.IntegrationOutbox{}).
		Where("id = ? AND status = ? AND locked_by = ?", id, model.OutboxSending, workerID).
		Updates(map[string]any{"status": model.OutboxFailed, "next_retry_at": nextRetryAt, "last_error": cause, "locked_by": nil, "locked_at": nil})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected != 1 {
		return fmt.Errorf("Outbox 事件发送锁已丢失")
	}
	return nil
}
