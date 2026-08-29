package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/repository"
)

const documentIndexEventType = "document.index.requested"

// ErrInvalidDocumentIndexEvent 表示消息格式或业务字段不满足稳定事件契约。
var ErrInvalidDocumentIndexEvent = errors.New("文档索引消息无效")

// DocumentIndexEvent 与 Logic Outbox 的 INDEX 消息载荷保持兼容。
type DocumentIndexEvent struct {
	SchemaVersion   int    `json:"schema_version"`
	EventID         string `json:"event_id"`
	EventType       string `json:"event_type"`
	DocumentID      uint64 `json:"document_id"`
	UserID          uint64 `json:"user_id"`
	KnowledgeBaseID uint64 `json:"knowledge_base_id"`
	IndexVersion    uint   `json:"index_version"`
	OccurredAt      string `json:"occurred_at"`
}

// DocumentIndexReceiver 将验证后的索引事件可靠写入本地待处理任务表。
type DocumentIndexReceiver struct{ repo *repository.DocumentTaskRepo }

// NewDocumentIndexReceiver 创建文档索引消息接收器。
func NewDocumentIndexReceiver(repo *repository.DocumentTaskRepo) *DocumentIndexReceiver {
	return &DocumentIndexReceiver{repo: repo}
}

// Receive 验证 INDEX 消息，并以 (document_id, index_version) 幂等记录任务。
func (r *DocumentIndexReceiver) Receive(ctx context.Context, body []byte) (bool, error) {
	event, err := parseDocumentIndexEvent(body)
	if err != nil {
		return false, err
	}
	return r.repo.RecordIndexRequest(ctx, event.EventID, event.DocumentID, event.IndexVersion, event.UserID, event.KnowledgeBaseID)
}

// parseDocumentIndexEvent 解析并校验来自 Logic 服务的稳定事件契约。
func parseDocumentIndexEvent(body []byte) (*DocumentIndexEvent, error) {
	var event DocumentIndexEvent
	if err := json.Unmarshal(body, &event); err != nil {
		return nil, fmt.Errorf("%w: 解析 JSON 失败: %v", ErrInvalidDocumentIndexEvent, err)
	}
	if event.SchemaVersion != 1 || event.EventType != documentIndexEventType || event.EventID == "" || event.DocumentID == 0 || event.UserID == 0 || event.KnowledgeBaseID == 0 || event.IndexVersion == 0 {
		return nil, fmt.Errorf("%w: 必填字段或事件类型不匹配", ErrInvalidDocumentIndexEvent)
	}
	if _, err := time.Parse(time.RFC3339Nano, event.OccurredAt); err != nil {
		return nil, fmt.Errorf("%w: 发生时间无效: %v", ErrInvalidDocumentIndexEvent, err)
	}
	return &event, nil
}
