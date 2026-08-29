package service

import (
	"context"
	"fmt"
	"log"
	"math"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/model"
)

// DocumentDownloadTicket 是执行解析时使用的短期下载授权和文件元数据。
type DocumentDownloadTicket struct {
	DownloadURL      string
	OriginalFilename string
	FileExtension    string
	ContentType      string
	FileSize         int64
	SHA256           string
	ExpiresAt        time.Time
}

// DocumentTicketProvider 为 Worker 获取与索引版本绑定的下载票据。
type DocumentTicketProvider interface {
	GetDocumentDownloadTicket(ctx context.Context, documentID uint64, indexVersion uint) (*DocumentDownloadTicket, error)
}

// DocumentTaskProcessor 执行下载、解析、切分和索引；成功返回才允许任务完成。
type DocumentTaskProcessor interface {
	ProcessDocument(ctx context.Context, task *model.DocumentIndexTask, ticket *DocumentDownloadTicket) error
}

// DocumentTaskRepository 提供 Worker 所需的原子领取和状态更新操作。
type DocumentTaskRepository interface {
	ClaimIndexTask(ctx context.Context, workerID string, lockTimeout time.Duration) (*model.DocumentIndexTask, error)
	MarkIndexTaskCompleted(ctx context.Context, id uint64, workerID string) error
	MarkIndexTaskFailed(ctx context.Context, id uint64, workerID string, nextRetryAt time.Time, cause string) error
}

// DocumentTaskWorkerConfig 描述任务轮询、锁恢复和失败退避参数。
type DocumentTaskWorkerConfig struct {
	WorkerID     string
	PollInterval time.Duration
	LockTimeout  time.Duration
	RetryBase    time.Duration
	RetryMax     time.Duration
}

// DocumentTaskWorker 可靠领取并执行 Agent 文档索引任务。
type DocumentTaskWorker struct {
	repo      DocumentTaskRepository
	tickets   DocumentTicketProvider
	processor DocumentTaskProcessor
	config    DocumentTaskWorkerConfig
}

// NewDocumentTaskWorker 创建文档索引任务 Worker。
func NewDocumentTaskWorker(repo DocumentTaskRepository, tickets DocumentTicketProvider, processor DocumentTaskProcessor, config DocumentTaskWorkerConfig) (*DocumentTaskWorker, error) {
	if repo == nil || tickets == nil || processor == nil || config.WorkerID == "" || config.PollInterval <= 0 || config.LockTimeout <= 0 || config.RetryBase <= 0 || config.RetryMax < config.RetryBase {
		return nil, fmt.Errorf("文档索引 Worker 配置无效")
	}
	return &DocumentTaskWorker{repo: repo, tickets: tickets, processor: processor, config: config}, nil
}

// Run 持续领取到期任务，直到上下文取消。
func (w *DocumentTaskWorker) Run(ctx context.Context) {
	ticker := time.NewTicker(w.config.PollInterval)
	defer ticker.Stop()
	for {
		w.processAvailable(ctx)
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

// processAvailable 在一次轮询中依次处理所有当前可领取任务。
func (w *DocumentTaskWorker) processAvailable(ctx context.Context) {
	for ctx.Err() == nil {
		task, err := w.repo.ClaimIndexTask(ctx, w.config.WorkerID, w.config.LockTimeout)
		if err != nil {
			log.Printf("领取文档索引任务失败: %v", err)
			return
		}
		if task == nil {
			return
		}
		ticket, err := w.tickets.GetDocumentDownloadTicket(ctx, task.DocumentID, task.IndexVersion)
		if err == nil {
			err = w.processor.ProcessDocument(ctx, task, ticket)
		}
		if err != nil {
			nextRetryAt := time.Now().Add(w.retryDelay(task.Attempts))
			if markErr := w.repo.MarkIndexTaskFailed(ctx, task.ID, w.config.WorkerID, nextRetryAt, err.Error()); markErr != nil {
				log.Printf("记录文档索引任务失败状态失败: task_id=%d err=%v", task.ID, markErr)
			}
			continue
		}
		if err := w.repo.MarkIndexTaskCompleted(ctx, task.ID, w.config.WorkerID); err != nil {
			log.Printf("标记文档索引任务完成失败: task_id=%d err=%v", task.ID, err)
		}
	}
}

// retryDelay 根据已尝试次数计算有上限的指数退避。
func (w *DocumentTaskWorker) retryDelay(attempts uint) time.Duration {
	exponent := math.Min(float64(attempts-1), 16)
	delay := time.Duration(float64(w.config.RetryBase) * math.Pow(2, exponent))
	if delay > w.config.RetryMax {
		return w.config.RetryMax
	}
	return delay
}
