package model

import "time"

const (
	ConversationActive     = 1
	MessageRoleUser        = 1
	MessageRoleAssistant   = 2
	MessageStatusStreaming = 1
	MessageStatusCompleted = 2
	MessageStatusFailed    = 3
	MessageStatusCancelled = 4
)

// Conversation 保存多轮问答的用户归属和知识库范围。
type Conversation struct {
	ID              string     `gorm:"column:id;primaryKey"`
	UserID          uint64     `gorm:"column:user_id"`
	KnowledgeBaseID uint64     `gorm:"column:knowledge_base_id"`
	Title           string     `gorm:"column:title"`
	Status          uint8      `gorm:"column:status"`
	LastMessageAt   *time.Time `gorm:"column:last_message_at"`
	CreatedAt       time.Time  `gorm:"column:created_at"`
	UpdatedAt       time.Time  `gorm:"column:updated_at"`
}

// TableName 返回 Agent 会话表名。
func (Conversation) TableName() string { return "agent_conversation" }

// ConversationMessage 保存一次用户输入或助手完整回答。
type ConversationMessage struct {
	ID             string     `gorm:"column:id;primaryKey"`
	ConversationID string     `gorm:"column:conversation_id"`
	RequestID      string     `gorm:"column:request_id"`
	Role           uint8      `gorm:"column:role"`
	Status         uint8      `gorm:"column:status"`
	Content        string     `gorm:"column:content"`
	Citations      *string    `gorm:"column:citations"`
	ErrorCode      *string    `gorm:"column:error_code"`
	ErrorMessage   *string    `gorm:"column:error_message"`
	CompletedAt    *time.Time `gorm:"column:completed_at"`
	CreatedAt      time.Time  `gorm:"column:created_at"`
	UpdatedAt      time.Time  `gorm:"column:updated_at"`
}

// TableName 返回 Agent 会话消息表名。
func (ConversationMessage) TableName() string { return "agent_conversation_message" }
