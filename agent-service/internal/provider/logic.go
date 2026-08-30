package provider

import (
	"context"
	"fmt"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/service"
	knowledgev1 "github.com/lijunsheng/familyos/proto/gen/knowledge/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

const internalTokenHeader = "x-familyos-internal-token"

// LogicClient 调用 Logic 的内部知识库接口。
type LogicClient struct {
	conn    *grpc.ClientConn
	client  knowledgev1.KnowledgeInternalServiceClient
	token   string
	timeout time.Duration
}

// NewLogicClient 创建 Logic 内部接口客户端。
func NewLogicClient(target, token string, timeout time.Duration) (*LogicClient, error) {
	if target == "" || token == "" || timeout <= 0 {
		return nil, fmt.Errorf("Logic 内部客户端配置无效")
	}
	conn, err := grpc.NewClient(target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, fmt.Errorf("连接 Logic 内部接口失败: %w", err)
	}
	return &LogicClient{conn: conn, client: knowledgev1.NewKnowledgeInternalServiceClient(conn), token: token, timeout: timeout}, nil
}

// GetDocumentDownloadTicket 获取与任务索引版本严格匹配的短期下载票据。
func (c *LogicClient) GetDocumentDownloadTicket(ctx context.Context, documentID uint64, indexVersion uint) (*service.DocumentDownloadTicket, error) {
	requestCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	requestCtx = metadata.AppendToOutgoingContext(requestCtx, internalTokenHeader, c.token)
	resp, err := c.client.GetDocumentDownloadTicket(requestCtx, &knowledgev1.GetDocumentDownloadTicketRequest{DocumentId: int64(documentID), IndexVersion: int32(indexVersion)})
	if err != nil {
		return nil, fmt.Errorf("请求 Logic 文档下载票据失败: %w", err)
	}
	if resp.GetCode() != 0 {
		return nil, fmt.Errorf("Logic 拒绝签发文档下载票据: code=%d message=%s", resp.GetCode(), resp.GetMessage())
	}
	expiresAt, err := time.Parse(time.RFC3339, resp.GetExpiresAt())
	if err != nil {
		return nil, fmt.Errorf("Logic 下载票据过期时间无效: %w", err)
	}
	if resp.GetDocumentId() != int64(documentID) || resp.GetIndexVersion() != int32(indexVersion) || resp.GetDownloadUrl() == "" || resp.GetFileSize() <= 0 || !expiresAt.After(time.Now()) {
		return nil, fmt.Errorf("Logic 下载票据响应无效")
	}
	return &service.DocumentDownloadTicket{DownloadURL: resp.GetDownloadUrl(), OriginalFilename: resp.GetOriginalFilename(), FileExtension: resp.GetFileExtension(), ContentType: resp.GetContentType(), FileSize: resp.GetFileSize(), SHA256: resp.GetSha256(), ExpiresAt: expiresAt}, nil
}

// CompleteDocumentIndex 通知 Logic 激活已经完整持久化的索引版本。
func (c *LogicClient) CompleteDocumentIndex(ctx context.Context, documentID uint64, indexVersion uint) error {
	requestCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	requestCtx = metadata.AppendToOutgoingContext(requestCtx, internalTokenHeader, c.token)
	resp, err := c.client.CompleteDocumentIndex(requestCtx, &knowledgev1.CompleteDocumentIndexRequest{DocumentId: int64(documentID), IndexVersion: int32(indexVersion)})
	if err != nil {
		return fmt.Errorf("通知 Logic 索引完成失败: %w", err)
	}
	if resp.GetCode() != 0 {
		return fmt.Errorf("Logic 拒绝激活索引版本: code=%d message=%s", resp.GetCode(), resp.GetMessage())
	}
	return nil
}

// FailDocumentIndex 通知 Logic 当前索引版本已经永久失败。
func (c *LogicClient) FailDocumentIndex(ctx context.Context, documentID uint64, indexVersion uint, failureCode, failureMessage string) error {
	requestCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	requestCtx = metadata.AppendToOutgoingContext(requestCtx, internalTokenHeader, c.token)
	resp, err := c.client.FailDocumentIndex(requestCtx, &knowledgev1.FailDocumentIndexRequest{DocumentId: int64(documentID), IndexVersion: int32(indexVersion), FailureCode: failureCode, FailureMessage: failureMessage})
	if err != nil {
		return fmt.Errorf("通知 Logic 索引永久失败失败: %w", err)
	}
	if resp.GetCode() != 0 {
		return fmt.Errorf("Logic 拒绝记录索引失败: code=%d message=%s", resp.GetCode(), resp.GetMessage())
	}
	return nil
}

// Close 关闭 Logic gRPC 连接。
func (c *LogicClient) Close() error { return c.conn.Close() }
