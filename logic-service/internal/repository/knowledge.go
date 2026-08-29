package repository

import (
	"context"
	"fmt"
	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
	"time"
)

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
func (r *KnowledgeRepo) CompleteUpload(ctx context.Context, documentID uint64, size uint64, etag string) (*model.KnowledgeDocument, error) {
	var document model.KnowledgeDocument
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.First(&document, documentID).Error; err != nil {
			return err
		}
		if document.Status != model.DocumentUploading {
			return nil
		}
		var session model.KnowledgeUploadSession
		if err := tx.Where("document_id = ?", documentID).First(&session).Error; err != nil {
			return err
		}
		if session.Status != model.UploadSessionPending || !session.ExpiresAt.After(time.Now()) {
			return fmt.Errorf("上传会话已过期")
		}
		now := time.Now()
		result := tx.Model(&model.KnowledgeDocument{}).Where("id = ? AND status = 0", documentID).Updates(map[string]any{"status": model.DocumentPending, "file_size": size, "oss_etag": etag, "uploaded_at": now})
		if result.Error != nil {
			return result.Error
		}
		if result.RowsAffected != 1 {
			return nil
		}
		if err := tx.Model(&model.KnowledgeUploadSession{}).Where("id = ? AND status = 0", session.ID).Updates(map[string]any{"status": model.UploadSessionConfirmed, "confirmed_at": now}).Error; err != nil {
			return err
		}
		payload := fmt.Sprintf(`{"schema_version":1,"event_type":"document.index.requested","document_id":%d,"knowledge_base_id":%d,"index_version":%d}`, documentID, document.KnowledgeBaseID, document.IndexVersion)
		eventID := fmt.Sprintf("%026d", time.Now().UnixNano())
		return tx.Create(&model.IntegrationOutbox{EventID: eventID, DedupKey: fmt.Sprintf("document:%d:index:%d", documentID, document.IndexVersion), AggregateType: "knowledge_document", AggregateID: documentID, EventType: "document.index.requested.v1", Topic: "familyos.rag.document", Tag: "INDEX", Payload: payload, Status: 0, Attempts: 0, NextRetryAt: time.Now()}).Error
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
