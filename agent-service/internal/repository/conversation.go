package repository

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/citation"
	"github.com/lijunsheng/familyos/agent-service/internal/model"
	"gorm.io/gorm"
)

// ConversationRepo 负责多轮会话和消息的事务持久化。
type ConversationRepo struct{ db *gorm.DB }

// NewConversationRepo 创建多轮会话仓储。
func NewConversationRepo(db *gorm.DB) *ConversationRepo { return &ConversationRepo{db: db} }

// Create 创建绑定用户和知识库的新会话。
func (r *ConversationRepo) Create(ctx context.Context, userID, knowledgeBaseID uint64) (*model.Conversation, error) {
	value := &model.Conversation{ID: uuid.NewString(), UserID: userID, KnowledgeBaseID: knowledgeBaseID, Status: model.ConversationActive}
	if err := r.db.WithContext(ctx).Create(value).Error; err != nil {
		return nil, fmt.Errorf("创建Agent会话失败: %w", err)
	}
	return value, nil
}

// BeginTurn 校验会话归属，并原子写入用户消息和生成中的助手消息。
func (r *ConversationRepo) BeginTurn(ctx context.Context, conversationID, requestID string, userID, knowledgeBaseID uint64, content string) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var count int64
		if err := tx.Model(&model.Conversation{}).Where("id = ? AND user_id = ? AND knowledge_base_id = ? AND status = ?", conversationID, userID, knowledgeBaseID, model.ConversationActive).Count(&count).Error; err != nil {
			return err
		}
		if count != 1 {
			return fmt.Errorf("会话不存在或无权访问")
		}
		now := time.Now()
		messages := []model.ConversationMessage{
			{ID: uuid.NewString(), ConversationID: conversationID, RequestID: requestID, Role: model.MessageRoleUser, Status: model.MessageStatusCompleted, Content: content, CompletedAt: &now},
			{ID: uuid.NewString(), ConversationID: conversationID, RequestID: requestID, Role: model.MessageRoleAssistant, Status: model.MessageStatusStreaming, Content: ""},
		}
		if err := tx.Create(&messages).Error; err != nil {
			return fmt.Errorf("保存会话消息失败: %w", err)
		}
		return tx.Model(&model.Conversation{}).Where("id = ?", conversationID).Updates(map[string]any{"last_message_at": now, "updated_at": now}).Error
	})
}

// RecentHistory 返回当前请求之前最近的已完成消息，结果按时间正序排列。
func (r *ConversationRepo) RecentHistory(ctx context.Context, conversationID, excludeRequestID string, limit int) ([]model.ConversationMessage, error) {
	var reversed []model.ConversationMessage
	err := r.db.WithContext(ctx).Where("conversation_id = ? AND request_id <> ? AND status = ?", conversationID, excludeRequestID, model.MessageStatusCompleted).Order("created_at DESC, role DESC, id DESC").Limit(limit).Find(&reversed).Error
	if err != nil {
		return nil, fmt.Errorf("读取会话历史失败: %w", err)
	}
	for left, right := 0, len(reversed)-1; left < right; left, right = left+1, right-1 {
		reversed[left], reversed[right] = reversed[right], reversed[left]
	}
	return reversed, nil
}

// CompleteAssistant 保存完整助手回答和引用快照。
func (r *ConversationRepo) CompleteAssistant(ctx context.Context, requestID, content string, citations []citation.Citation) error {
	encoded, err := json.Marshal(citations)
	if err != nil {
		return fmt.Errorf("编码回答引用失败: %w", err)
	}
	value, now := string(encoded), time.Now()
	result := r.db.WithContext(ctx).Model(&model.ConversationMessage{}).Where("request_id = ? AND role = ? AND status = ?", requestID, model.MessageRoleAssistant, model.MessageStatusStreaming).Updates(map[string]any{"status": model.MessageStatusCompleted, "content": content, "citations": value, "completed_at": now})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected != 1 {
		return fmt.Errorf("助手消息状态已变化")
	}
	return nil
}

// FailAssistant 将生成中的助手消息更新为失败或取消状态。
func (r *ConversationRepo) FailAssistant(ctx context.Context, requestID string, cancelled bool, cause error) error {
	status, code := model.MessageStatusFailed, "GENERATION_FAILED"
	if cancelled {
		status, code = model.MessageStatusCancelled, "GENERATION_CANCELLED"
	}
	message, now := cause.Error(), time.Now()
	if len(message) > 500 {
		message = message[:500]
	}
	return r.db.WithContext(ctx).Model(&model.ConversationMessage{}).Where("request_id = ? AND role = ? AND status = ?", requestID, model.MessageRoleAssistant, model.MessageStatusStreaming).Updates(map[string]any{"status": status, "error_code": code, "error_message": message, "completed_at": now}).Error
}
