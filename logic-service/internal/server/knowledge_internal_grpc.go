package server

import (
	"context"
	"crypto/subtle"
	"errors"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/service"
	knowledgev1 "github.com/lijunsheng/familyos/proto/gen/knowledge/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

const internalTokenHeader = "x-familyos-internal-token"

// KnowledgeInternalServer 向受信任的 Agent 提供文档短期下载票据。
type KnowledgeInternalServer struct {
	knowledgev1.UnimplementedKnowledgeInternalServiceServer
	svc         *service.KnowledgeService
	agentToken  string
	downloadTTL time.Duration
}

// NewKnowledgeInternalServer 创建带服务令牌鉴权的知识库内部接口。
func NewKnowledgeInternalServer(svc *service.KnowledgeService, agentToken string, downloadTTL time.Duration) *KnowledgeInternalServer {
	return &KnowledgeInternalServer{svc: svc, agentToken: agentToken, downloadTTL: downloadTTL}
}

// GetDocumentDownloadTicket 校验调用方身份，并为指定索引版本签发一次短期下载票据。
func (s *KnowledgeInternalServer) GetDocumentDownloadTicket(ctx context.Context, req *knowledgev1.GetDocumentDownloadTicketRequest) (*knowledgev1.GetDocumentDownloadTicketResponse, error) {
	values := metadata.ValueFromIncomingContext(ctx, internalTokenHeader)
	if s.agentToken == "" || len(values) != 1 || len(values[0]) != len(s.agentToken) || subtle.ConstantTimeCompare([]byte(values[0]), []byte(s.agentToken)) != 1 {
		return nil, status.Error(codes.Unauthenticated, "内部服务身份校验失败")
	}
	if req == nil || req.GetDocumentId() <= 0 || req.GetIndexVersion() <= 0 {
		return &knowledgev1.GetDocumentDownloadTicketResponse{Code: 4001, Message: service.ErrKnowledgeInvalid.Error()}, nil
	}
	ticket, err := s.svc.GetDocumentDownloadTicket(ctx, uint64(req.GetDocumentId()), uint(req.GetIndexVersion()), s.downloadTTL)
	if err != nil {
		code := int32(CodeInternalError)
		switch {
		case errors.Is(err, service.ErrKnowledgeInvalid):
			code = 4001
		case errors.Is(err, service.ErrKnowledgeVersionStale):
			code = 4091
		case errors.Is(err, service.ErrKnowledgeNotFound):
			code = 4004
		case errors.Is(err, service.ErrKnowledgeNotReady):
			code = 4092
		}
		return &knowledgev1.GetDocumentDownloadTicketResponse{Code: code, Message: err.Error()}, nil
	}
	return &knowledgev1.GetDocumentDownloadTicketResponse{Code: CodeSuccess, Message: "下载票据创建成功", DocumentId: int64(ticket.DocumentID), IndexVersion: int32(ticket.IndexVersion), DownloadUrl: ticket.DownloadURL, OriginalFilename: ticket.OriginalFilename, FileExtension: ticket.FileExtension, ContentType: ticket.ContentType, FileSize: int64(ticket.FileSize), Sha256: ticket.SHA256, ExpiresAt: ticket.ExpiresAt.Format(time.RFC3339)}, nil
}
