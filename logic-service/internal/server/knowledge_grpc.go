package server

import (
	"context"
	"errors"
	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/service"
	knowledgev1 "github.com/lijunsheng/familyos/proto/gen/knowledge/v1"
)

// KnowledgeServer 提供知识库文档上传接口。
type KnowledgeServer struct {
	knowledgev1.UnimplementedKnowledgeServiceServer
	svc *service.KnowledgeService
}

// EnsurePersonalKnowledgeBase 获取或创建个人知识库。
func (s *KnowledgeServer) EnsurePersonalKnowledgeBase(ctx context.Context, req *knowledgev1.EnsurePersonalKnowledgeBaseRequest) (*knowledgev1.EnsurePersonalKnowledgeBaseResponse, error) {
	base, err := s.svc.EnsurePersonalKnowledgeBase(ctx, uint64(req.GetUserId()))
	if err != nil {
		return &knowledgev1.EnsurePersonalKnowledgeBaseResponse{Code: 4003, Message: err.Error()}, nil
	}
	return &knowledgev1.EnsurePersonalKnowledgeBaseResponse{Code: 0, Message: "查询成功", KnowledgeBaseId: int64(base.ID)}, nil
}

// NewKnowledgeServer 创建知识库 gRPC 服务。
func NewKnowledgeServer(svc *service.KnowledgeService) *KnowledgeServer {
	return &KnowledgeServer{svc: svc}
}

// CreateUploadTicket 创建 OSS 直传票据。
func (s *KnowledgeServer) CreateUploadTicket(ctx context.Context, req *knowledgev1.CreateUploadTicketRequest) (*knowledgev1.CreateUploadTicketResponse, error) {
	id, sid, signed, err := s.svc.CreateUploadTicket(ctx, uint64(req.GetUserId()), uint64(req.GetKnowledgeBaseId()), req.GetFilename(), req.GetContentType(), req.GetFileSize(), req.GetSha256())
	if err != nil {
		code := int32(CodeInternalError)
		if errors.Is(err, service.ErrKnowledgeInvalid) {
			code = 4001
		}
		if errors.Is(err, service.ErrKnowledgePermission) {
			code = 4003
		}
		if errors.Is(err, service.ErrKnowledgeNotFound) {
			code = 4004
		}
		return &knowledgev1.CreateUploadTicketResponse{Code: code, Message: err.Error()}, nil
	}
	return &knowledgev1.CreateUploadTicketResponse{Code: 0, Message: "上传票据创建成功", DocumentId: int64(id), UploadSessionId: sid, UploadUrl: signed.URL, Method: "PUT", RequiredHeaders: signed.Headers, ExpiresAt: signed.ExpiresAt.Format("2006-01-02T15:04:05Z07:00")}, nil
}

// CompleteUpload 确认 OSS 上传并提交索引任务。
func (s *KnowledgeServer) CompleteUpload(ctx context.Context, req *knowledgev1.CompleteUploadRequest) (*knowledgev1.CompleteUploadResponse, error) {
	doc, err := s.svc.CompleteUpload(ctx, uint64(req.GetUserId()), uint64(req.GetDocumentId()))
	if err != nil {
		return &knowledgev1.CompleteUploadResponse{Code: 4001, Message: err.Error()}, nil
	}
	return &knowledgev1.CompleteUploadResponse{Code: 0, Message: "文档已提交处理", DocumentId: int64(doc.ID), Status: int32(doc.Status), IndexVersion: int32(doc.IndexVersion)}, nil
}

// DeleteDocument 请求删除文档并投递向量清理事件。
func (s *KnowledgeServer) DeleteDocument(ctx context.Context, req *knowledgev1.DeleteDocumentRequest) (*knowledgev1.DeleteDocumentResponse, error) {
	doc, err := s.svc.DeleteDocument(ctx, uint64(req.GetUserId()), uint64(req.GetDocumentId()))
	if err != nil {
		code := int32(CodeInternalError)
		if errors.Is(err, service.ErrKnowledgeNotFound) {
			code = 4004
		}
		if errors.Is(err, service.ErrKnowledgePermission) {
			code = 4003
		}
		return &knowledgev1.DeleteDocumentResponse{Code: code, Message: err.Error()}, nil
	}
	return &knowledgev1.DeleteDocumentResponse{Code: CodeSuccess, Message: "文档删除已提交", DocumentId: int64(doc.ID), Status: int32(model.DocumentDeleting)}, nil
}
