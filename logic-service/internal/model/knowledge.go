package model

import "time"

const (
	KnowledgeScopePersonal int8 = 1
	KnowledgeScopeFamily   int8 = 2

	DocumentUploading  int8 = 0
	DocumentPending    int8 = 1
	DocumentProcessing int8 = 2
	DocumentCompleted  int8 = 3
	DocumentFailed     int8 = 4
	DocumentDeleting   int8 = 5
	DocumentDeleted    int8 = 6

	UploadSessionPending   int8 = 0
	UploadSessionConfirmed int8 = 1
	UploadSessionCancelled int8 = 2
	UploadSessionExpired   int8 = 3
)

// KnowledgeBase 描述个人或家庭共享的知识库。
type KnowledgeBase struct {
	ID          uint64  `gorm:"column:id;primaryKey"`
	ScopeType   int8    `gorm:"column:scope_type"`
	OwnerUserID *uint64 `gorm:"column:owner_user_id"`
	FamilyID    *uint64 `gorm:"column:family_id"`
	Name        string  `gorm:"column:name"`
	Status      int8    `gorm:"column:status"`
	IsDefault   int8    `gorm:"column:is_default"`
	CreatedBy   uint64  `gorm:"column:created_by"`
}

// TableName 返回知识库表名。
func (KnowledgeBase) TableName() string { return "knowledge_base" }

// KnowledgeDocument 记录知识库文档的上传和索引状态。
type KnowledgeDocument struct {
	ID                 uint64     `gorm:"column:id;primaryKey"`
	KnowledgeBaseID    uint64     `gorm:"column:knowledge_base_id"`
	CreatedBy          uint64     `gorm:"column:created_by"`
	Title              string     `gorm:"column:title"`
	OriginalFilename   string     `gorm:"column:original_filename"`
	FileExtension      string     `gorm:"column:file_extension"`
	MimeType           string     `gorm:"column:mime_type"`
	FileSize           *uint64    `gorm:"column:file_size"`
	FileSHA256         *string    `gorm:"column:file_sha256"`
	OSSBucket          string     `gorm:"column:oss_bucket"`
	OSSObjectKey       string     `gorm:"column:oss_object_key"`
	OSSETag            *string    `gorm:"column:oss_etag"`
	Status             int8       `gorm:"column:status"`
	IndexVersion       uint       `gorm:"column:index_version"`
	ActiveIndexVersion uint       `gorm:"column:active_index_version"`
	UploadExpiresAt    *time.Time `gorm:"column:upload_expires_at"`
	UploadedAt         *time.Time `gorm:"column:uploaded_at"`
}

// TableName 返回文档表名。
func (KnowledgeDocument) TableName() string { return "knowledge_document" }

// KnowledgeUploadSession 绑定一次临时 OSS 上传授权和目标文档。
type KnowledgeUploadSession struct {
	ID               string    `gorm:"column:id;primaryKey"`
	KnowledgeBaseID  uint64    `gorm:"column:knowledge_base_id"`
	DocumentID       uint64    `gorm:"column:document_id"`
	CreatedBy        uint64    `gorm:"column:created_by"`
	OSSBucket        string    `gorm:"column:oss_bucket"`
	OSSObjectKey     string    `gorm:"column:oss_object_key"`
	OriginalFilename string    `gorm:"column:original_filename"`
	DeclaredMimeType string    `gorm:"column:declared_mime_type"`
	DeclaredFileSize uint64    `gorm:"column:declared_file_size"`
	DeclaredSHA256   *string   `gorm:"column:declared_sha256"`
	Status           int8      `gorm:"column:status"`
	ExpiresAt        time.Time `gorm:"column:expires_at"`
}

// TableName 返回上传会话表名。
func (KnowledgeUploadSession) TableName() string { return "knowledge_upload_session" }

// IntegrationOutbox 保存数据库事务提交后待发布的集成事件。
type IntegrationOutbox struct {
	ID            uint64     `gorm:"column:id;primaryKey"`
	EventID       string     `gorm:"column:event_id"`
	DedupKey      string     `gorm:"column:dedup_key"`
	AggregateType string     `gorm:"column:aggregate_type"`
	AggregateID   uint64     `gorm:"column:aggregate_id"`
	EventType     string     `gorm:"column:event_type"`
	Topic         string     `gorm:"column:topic"`
	Tag           string     `gorm:"column:tag"`
	Payload       string     `gorm:"column:payload"`
	Status        int8       `gorm:"column:status"`
	Attempts      uint       `gorm:"column:attempts"`
	NextRetryAt   time.Time  `gorm:"column:next_retry_at"`
	LockedBy      *string    `gorm:"column:locked_by"`
	LockedAt      *time.Time `gorm:"column:locked_at"`
}

// TableName 返回 Outbox 表名。
func (IntegrationOutbox) TableName() string { return "integration_outbox" }
