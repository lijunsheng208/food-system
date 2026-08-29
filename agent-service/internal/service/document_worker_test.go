package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/model"
)

type workerRepoStub struct {
	task      *model.DocumentIndexTask
	completed bool
	failed    bool
	failure   string
}

// ClaimIndexTask 返回一次测试任务，模拟仓储的领取行为。
func (r *workerRepoStub) ClaimIndexTask(context.Context, string, time.Duration) (*model.DocumentIndexTask, error) {
	task := r.task
	r.task = nil
	return task, nil
}

// MarkIndexTaskCompleted 记录 Worker 的成功状态更新。
func (r *workerRepoStub) MarkIndexTaskCompleted(context.Context, uint64, string) error {
	r.completed = true
	return nil
}

// MarkIndexTaskFailed 记录 Worker 的失败状态和原因。
func (r *workerRepoStub) MarkIndexTaskFailed(_ context.Context, _ uint64, _ string, _ time.Time, cause string) error {
	r.failed, r.failure = true, cause
	return nil
}

type ticketProviderStub struct{ err error }

// GetDocumentDownloadTicket 返回测试票据或预设错误。
func (p ticketProviderStub) GetDocumentDownloadTicket(context.Context, uint64, uint) (*DocumentDownloadTicket, error) {
	if p.err != nil {
		return nil, p.err
	}
	return &DocumentDownloadTicket{DownloadURL: "https://example.invalid/signed", FileSize: 10, ExpiresAt: time.Now().Add(time.Minute)}, nil
}

// CompleteDocumentIndex 模拟 Logic 成功激活索引版本。
func (p ticketProviderStub) CompleteDocumentIndex(context.Context, uint64, uint) error { return nil }

type processorStub struct {
	err    error
	called bool
}

// ProcessDocument 记录处理器是否被调用并返回预设结果。
func (p *processorStub) ProcessDocument(context.Context, *model.DocumentIndexTask, *DocumentDownloadTicket) error {
	p.called = true
	return p.err
}

// TestDocumentTaskWorkerCompletesOnlyAfterProcessing 验证处理器成功后才完成任务。
func TestDocumentTaskWorkerCompletesOnlyAfterProcessing(t *testing.T) {
	repo := &workerRepoStub{task: &model.DocumentIndexTask{ID: 1, DocumentID: 2, IndexVersion: 1, Attempts: 1}}
	processor := &processorStub{}
	worker, err := NewDocumentTaskWorker(repo, ticketProviderStub{}, processor, validWorkerConfig())
	if err != nil {
		t.Fatalf("创建 Worker 失败: %v", err)
	}
	worker.processAvailable(context.Background())
	if !processor.called || !repo.completed || repo.failed {
		t.Fatalf("任务状态不正确: processor=%v completed=%v failed=%v", processor.called, repo.completed, repo.failed)
	}
}

// TestDocumentTaskWorkerRetriesTicketFailure 验证获取票据失败时不会调用解析器，并安排任务重试。
func TestDocumentTaskWorkerRetriesTicketFailure(t *testing.T) {
	repo := &workerRepoStub{task: &model.DocumentIndexTask{ID: 1, DocumentID: 2, IndexVersion: 1, Attempts: 1}}
	processor := &processorStub{}
	worker, err := NewDocumentTaskWorker(repo, ticketProviderStub{err: errors.New("ticket unavailable")}, processor, validWorkerConfig())
	if err != nil {
		t.Fatalf("创建 Worker 失败: %v", err)
	}
	worker.processAvailable(context.Background())
	if processor.called || repo.completed || !repo.failed || repo.failure == "" {
		t.Fatalf("任务状态不正确: processor=%v completed=%v failed=%v error=%q", processor.called, repo.completed, repo.failed, repo.failure)
	}
}

// validWorkerConfig 返回测试使用的最小有效 Worker 配置。
func validWorkerConfig() DocumentTaskWorkerConfig {
	return DocumentTaskWorkerConfig{WorkerID: "worker-test", PollInterval: time.Second, LockTimeout: time.Minute, RetryBase: time.Second, RetryMax: time.Minute}
}
