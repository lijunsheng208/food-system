package provider

import (
	"context"
	"fmt"
	"time"

	"github.com/lijunsheng/familyos/agent-service/internal/service"
	authv1 "github.com/lijunsheng/familyos/proto/gen/auth/v1"
	dishv1 "github.com/lijunsheng/familyos/proto/gen/dish/v1"
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
	auth    authv1.AuthServiceClient
	dish    dishv1.DishServiceClient
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
	return &LogicClient{conn: conn, client: knowledgev1.NewKnowledgeInternalServiceClient(conn), auth: authv1.NewAuthServiceClient(conn), dish: dishv1.NewDishServiceClient(conn), token: token, timeout: timeout}, nil
}

// ListDietaryPreferences 查询指定用户的个人饮食偏好，用户 ID 由服务端请求状态注入。
func (c *LogicClient) ListDietaryPreferences(ctx context.Context, userID uint64) ([]*authv1.DietaryPreferenceInfo, error) {
	if userID == 0 {
		return nil, fmt.Errorf("查询饮食偏好用户无效")
	}
	requestCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	requestCtx = metadata.AppendToOutgoingContext(requestCtx, internalTokenHeader, c.token)
	resp, err := c.auth.ListDietaryPreferences(requestCtx, &authv1.ListDietaryPreferencesRequest{UserId: int64(userID)})
	if err != nil {
		return nil, fmt.Errorf("请求 Logic 饮食偏好失败: %w", err)
	}
	if resp.GetCode() != 0 {
		return nil, fmt.Errorf("Logic 拒绝查询饮食偏好: code=%d message=%s", resp.GetCode(), resp.GetMessage())
	}
	return resp.GetPreferences(), nil
}

// SearchDishes 按关键字搜索系统中已上架的菜谱。
func (c *LogicClient) SearchDishes(ctx context.Context, keyword string) ([]*dishv1.DishInfo, error) {
	if keyword == "" {
		return nil, fmt.Errorf("菜谱搜索关键字不能为空")
	}
	requestCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	requestCtx = metadata.AppendToOutgoingContext(requestCtx, internalTokenHeader, c.token)
	resp, err := c.dish.SearchDishes(requestCtx, &dishv1.SearchDishesRequest{Keyword: keyword})
	if err != nil {
		return nil, fmt.Errorf("请求 Logic 菜谱搜索失败: %w", err)
	}
	if resp.GetCode() != 0 {
		return nil, fmt.Errorf("Logic 拒绝搜索菜谱: code=%d message=%s", resp.GetCode(), resp.GetMessage())
	}
	return resp.GetDishes(), nil
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
