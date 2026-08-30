package model

import "time"

const (
	// DocumentIndexTaskPending 表示消息已落库，等待后续解析 Worker 领取。
	DocumentIndexTaskPending int8 = 0
	// DocumentIndexTaskProcessing 表示任务已被一个 Worker 独占领取。
	DocumentIndexTaskProcessing int8 = 1
	// DocumentIndexTaskRetryWait 表示本次执行失败，等待退避后重试。
	DocumentIndexTaskRetryWait int8 = 2
	// DocumentIndexTaskCompleted 表示当前索引版本已经处理完成。
	DocumentIndexTaskCompleted int8 = 3
	// DocumentIndexTaskFailedPermanent 表示任务不可重试或已达到最大尝试次数。
	DocumentIndexTaskFailedPermanent int8 = 4
)

// DocumentIndexTask 保存已可靠接收、但尚未解析的文档索引任务。
type DocumentIndexTask struct {
	ID              uint64     `gorm:"column:id;primaryKey"`
	EventID         string     `gorm:"column:event_id"`
	DocumentID      uint64     `gorm:"column:document_id"`
	IndexVersion    uint       `gorm:"column:index_version"`
	UserID          uint64     `gorm:"column:user_id"`
	KnowledgeBaseID uint64     `gorm:"column:knowledge_base_id"`
	Status          int8       `gorm:"column:status"`
	ReceivedAt      time.Time  `gorm:"column:received_at"`
	Attempts        uint       `gorm:"column:attempts"`
	NextRetryAt     time.Time  `gorm:"column:next_retry_at"`
	LockedBy        *string    `gorm:"column:locked_by"`
	LockedAt        *time.Time `gorm:"column:locked_at"`
	LastError       *string    `gorm:"column:last_error"`
	FailureCode     *string    `gorm:"column:failure_code"`
	FailureMessage  *string    `gorm:"column:failure_message"`
	StartedAt       *time.Time `gorm:"column:started_at"`
	CompletedAt     *time.Time `gorm:"column:completed_at"`
}

// TableName 返回 Agent 索引任务表名。
func (DocumentIndexTask) TableName() string { return "agent_document_index_task" }
