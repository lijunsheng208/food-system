package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/model"
)

type workerRepoStub struct {
	task          *model.DocumentIndexTask
	completed     bool
	retryWait     bool
	permanent     bool
	reportPending bool
	failure       string
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

// MarkIndexTaskRetryWait 记录 Worker 的可重试状态和原因。
func (r *workerRepoStub) MarkIndexTaskRetryWait(_ context.Context, _ uint64, _ string, _ time.Time, cause string) error {
	r.retryWait, r.failure = true, cause
	return nil
}

// MarkIndexTaskFailureReportPending 记录仅等待 Logic 失败回调的任务。
func (r *workerRepoStub) MarkIndexTaskFailureReportPending(_ context.Context, _ uint64, _ string, _, _, cause string, _ time.Time) error {
	r.reportPending, r.failure = true, cause
	return nil
}

// MarkIndexTaskFailedPermanent 记录 Worker 的永久失败状态。
func (r *workerRepoStub) MarkIndexTaskFailedPermanent(_ context.Context, _ uint64, _, cause string) error {
	r.permanent, r.failure = true, cause
	return nil
}

type ticketProviderStub struct {
	err, failErr    error
	failureReported *bool
}

// GetDocumentDownloadTicket 返回测试票据或预设错误。
func (p ticketProviderStub) GetDocumentDownloadTicket(context.Context, uint64, uint) (*DocumentDownloadTicket, error) {
	if p.err != nil {
		return nil, p.err
	}
	return &DocumentDownloadTicket{DownloadURL: "https://example.invalid/signed", FileSize: 10, ExpiresAt: time.Now().Add(time.Minute)}, nil
}

// CompleteDocumentIndex 模拟 Logic 成功激活索引版本。
func (p ticketProviderStub) CompleteDocumentIndex(context.Context, uint64, uint) error { return nil }

// FailDocumentIndex 模拟向 Logic 上报永久失败。
func (p ticketProviderStub) FailDocumentIndex(context.Context, uint64, uint, string, string) error {
	if p.failureReported != nil {
		*p.failureReported = true
	}
	return p.failErr
}

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
	if !processor.called || !repo.completed || repo.retryWait || repo.permanent {
		t.Fatalf("任务状态不正确: processor=%v completed=%v retry=%v permanent=%v", processor.called, repo.completed, repo.retryWait, repo.permanent)
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
	if processor.called || repo.completed || !repo.retryWait || repo.failure == "" {
		t.Fatalf("任务状态不正确: processor=%v completed=%v retry=%v error=%q", processor.called, repo.completed, repo.retryWait, repo.failure)
	}
}

// TestDocumentTaskWorkerStopsPermanentFailure 验证不可重试错误立即上报 Logic 并进入永久失败。
func TestDocumentTaskWorkerStopsPermanentFailure(t *testing.T) {
	repo := &workerRepoStub{task: &model.DocumentIndexTask{ID: 1, DocumentID: 2, IndexVersion: 1, Attempts: 1}}
	processor := &processorStub{err: NewPermanentDocumentError("DOCUMENT_EMPTY", "文档解析结果为空", nil)}
	reported := false
	worker, err := NewDocumentTaskWorker(repo, ticketProviderStub{failureReported: &reported}, processor, validWorkerConfig())
	if err != nil {
		t.Fatalf("创建 Worker 失败: %v", err)
	}
	worker.processAvailable(context.Background())
	if !reported || !repo.permanent || repo.retryWait {
		t.Fatalf("永久失败状态不正确: reported=%v permanent=%v retry=%v", reported, repo.permanent, repo.retryWait)
	}
}

// TestDocumentTaskWorkerStopsAfterMaxAttempts 验证可重试错误达到上限后转为永久失败。
func TestDocumentTaskWorkerStopsAfterMaxAttempts(t *testing.T) {
	repo := &workerRepoStub{task: &model.DocumentIndexTask{ID: 1, DocumentID: 2, IndexVersion: 1, Attempts: 5}}
	processor := &processorStub{err: errors.New("embedding timeout")}
	reported := false
	worker, err := NewDocumentTaskWorker(repo, ticketProviderStub{failureReported: &reported}, processor, validWorkerConfig())
	if err != nil {
		t.Fatalf("创建 Worker 失败: %v", err)
	}
	worker.processAvailable(context.Background())
	if !reported || !repo.permanent || repo.retryWait {
		t.Fatalf("重试上限状态不正确: reported=%v permanent=%v retry=%v", reported, repo.permanent, repo.retryWait)
	}
}

// TestDocumentTaskWorkerRetriesOnlyFailureCallback 验证 Logic 回调失败后不会再次执行文档处理。
func TestDocumentTaskWorkerRetriesOnlyFailureCallback(t *testing.T) {
	code, message := "DOCUMENT_EMPTY", "文档解析结果为空"
	repo := &workerRepoStub{task: &model.DocumentIndexTask{ID: 1, DocumentID: 2, IndexVersion: 1, Attempts: 2, FailureCode: &code, FailureMessage: &message}}
	processor := &processorStub{}
	reported := false
	worker, err := NewDocumentTaskWorker(repo, ticketProviderStub{failureReported: &reported}, processor, validWorkerConfig())
	if err != nil {
		t.Fatalf("创建 Worker 失败: %v", err)
	}
	worker.processAvailable(context.Background())
	if processor.called || !reported || !repo.permanent {
		t.Fatalf("失败回调重试不正确: processor=%v reported=%v permanent=%v", processor.called, reported, repo.permanent)
	}
}

// validWorkerConfig 返回测试使用的最小有效 Worker 配置。
func validWorkerConfig() DocumentTaskWorkerConfig {
	return DocumentTaskWorkerConfig{WorkerID: "worker-test", PollInterval: time.Second, LockTimeout: time.Minute, RetryBase: time.Second, RetryMax: time.Minute, MaxAttempts: 5}
}
