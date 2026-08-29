package service

import (
	"context"
	"fmt"
	"log"
	"math"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
)

// OutboxSender 抽象消息中间件发送，便于独立测试 Publisher 的可靠状态机。
type OutboxSender interface {
	Send(ctx context.Context, topic, tag, key string, body []byte) error
}

// OutboxPublisherConfig 描述轮询、锁恢复和退避策略。
type OutboxPublisherConfig struct {
	WorkerID     string
	PollInterval time.Duration
	LockTimeout  time.Duration
	RetryBase    time.Duration
	RetryMax     time.Duration
}

// OutboxPublisher 从 MySQL Outbox 可靠发布集成事件。
type OutboxPublisher struct {
	repo   *repository.KnowledgeRepo
	sender OutboxSender
	config OutboxPublisherConfig
}

// NewOutboxPublisher 创建 Outbox Publisher。
func NewOutboxPublisher(repo *repository.KnowledgeRepo, sender OutboxSender, config OutboxPublisherConfig) (*OutboxPublisher, error) {
	if repo == nil || sender == nil || config.WorkerID == "" || config.PollInterval <= 0 || config.LockTimeout <= 0 || config.RetryBase <= 0 || config.RetryMax < config.RetryBase {
		return nil, fmt.Errorf("Outbox Publisher 配置无效")
	}
	return &OutboxPublisher{repo: repo, sender: sender, config: config}, nil
}

// Run 持续发布到期事件，直到服务上下文取消。
func (p *OutboxPublisher) Run(ctx context.Context) {
	ticker := time.NewTicker(p.config.PollInterval)
	defer ticker.Stop()
	for {
		p.publishAvailable(ctx)
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

// publishAvailable 在单次轮询内尽可能清空已到期事件。
func (p *OutboxPublisher) publishAvailable(ctx context.Context) {
	for {
		event, err := p.repo.ClaimOutboxEvent(ctx, p.config.WorkerID, p.config.LockTimeout)
		if err != nil {
			log.Printf("抢占 Outbox 事件失败: %v", err)
			return
		}
		if event == nil {
			return
		}
		if err := p.sender.Send(ctx, event.Topic, event.Tag, event.EventID, []byte(event.Payload)); err != nil {
			nextRetryAt := time.Now().Add(p.retryDelay(event.Attempts))
			if markErr := p.repo.MarkOutboxFailed(ctx, event.ID, p.config.WorkerID, nextRetryAt, err.Error()); markErr != nil {
				log.Printf("记录 Outbox 发送失败状态失败: event_id=%s err=%v", event.EventID, markErr)
			}
			continue
		}
		if err := p.repo.MarkOutboxSent(ctx, event.ID, p.config.WorkerID); err != nil {
			log.Printf("标记 Outbox 已发送失败: event_id=%s err=%v", event.EventID, err)
		}
	}
}

// retryDelay 根据已尝试次数计算有上限的指数退避。
func (p *OutboxPublisher) retryDelay(attempts uint) time.Duration {
	exponent := math.Min(float64(attempts-1), 16)
	delay := time.Duration(float64(p.config.RetryBase) * math.Pow(2, exponent))
	if delay > p.config.RetryMax {
		return p.config.RetryMax
	}
	return delay
}

// DocumentIndexEvent 表示文档索引请求的稳定消息载荷。
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

// DocumentDeleteEvent 表示请求删除文档全部索引版本的稳定消息载荷。
type DocumentDeleteEvent struct {
	SchemaVersion     int    `json:"schema_version"`
	EventID           string `json:"event_id"`
	EventType         string `json:"event_type"`
	DocumentID        uint64 `json:"document_id"`
	UserID            uint64 `json:"user_id"`
	KnowledgeBaseID   uint64 `json:"knowledge_base_id"`
	DeleteAllVersions bool   `json:"delete_all_versions"`
	OccurredAt        string `json:"occurred_at"`
}

var _ = model.OutboxPending
