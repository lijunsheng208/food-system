package model

import "time"

const (
	// DocumentIndexTaskPending 表示消息已落库，等待后续解析 Worker 领取。
	DocumentIndexTaskPending int8 = 0
)

// DocumentIndexTask 保存已可靠接收、但尚未解析的文档索引任务。
type DocumentIndexTask struct {
	ID              uint64    `gorm:"column:id;primaryKey"`
	EventID         string    `gorm:"column:event_id"`
	DocumentID      uint64    `gorm:"column:document_id"`
	IndexVersion    uint      `gorm:"column:index_version"`
	UserID          uint64    `gorm:"column:user_id"`
	KnowledgeBaseID uint64    `gorm:"column:knowledge_base_id"`
	Status          int8      `gorm:"column:status"`
	ReceivedAt      time.Time `gorm:"column:received_at"`
}

// TableName 返回 Agent 索引任务表名。
func (DocumentIndexTask) TableName() string { return "agent_document_index_task" }
