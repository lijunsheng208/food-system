package handler

import (
	"context"
	"github.com/gin-gonic/gin"
	"github.com/lijunsheng/familyos/gateway-service/internal/middleware"
	knowledgev1 "github.com/lijunsheng/familyos/proto/gen/knowledge/v1"
	"google.golang.org/grpc"
	"log"
	"net/http"
	"strconv"
	"time"
)

// KnowledgeHandler 转换知识库上传 HTTP 请求为 gRPC 调用。
type KnowledgeHandler struct {
	client knowledgev1.KnowledgeServiceClient
}

// EnsurePersonalKnowledgeBase 获取或创建当前用户的个人知识库。
func (h *KnowledgeHandler) EnsurePersonalKnowledgeBase(c *gin.Context) {
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.EnsurePersonalKnowledgeBase(ctx, &knowledgev1.EnsurePersonalKnowledgeBaseRequest{UserId: int64(middleware.CurrentUserID(c))})
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 1999, "message": "知识库服务暂不可用"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "knowledge_base_id": resp.GetKnowledgeBaseId()})
}

// NewKnowledgeHandler 创建处理器。
func NewKnowledgeHandler(conn *grpc.ClientConn) *KnowledgeHandler {
	return &KnowledgeHandler{client: knowledgev1.NewKnowledgeServiceClient(conn)}
}

// CreateUploadTicket POST /api/v1/knowledge-bases/:id/documents/upload-ticket
func (h *KnowledgeHandler) CreateUploadTicket(c *gin.Context) {
	baseID, _ := strconv.ParseUint(c.Param("id"), 10, 64)
	var body struct {
		Filename    string `json:"filename"`
		ContentType string `json:"content_type"`
		FileSize    int64  `json:"file_size"`
		SHA256      string `json:"sha256"`
	}
	if c.ShouldBindJSON(&body) != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请求格式错误"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
	defer cancel()
	resp, err := h.client.CreateUploadTicket(ctx, &knowledgev1.CreateUploadTicketRequest{UserId: int64(middleware.CurrentUserID(c)), KnowledgeBaseId: int64(baseID), Filename: body.Filename, ContentType: body.ContentType, FileSize: body.FileSize, Sha256: body.SHA256})
	if err != nil {
		log.Printf("CreateUploadTicket gRPC 调用失败: %v", err)
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 1999, "message": "上传服务暂不可用"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "data": gin.H{"document_id": resp.GetDocumentId(), "upload_session_id": resp.GetUploadSessionId(), "upload_url": resp.GetUploadUrl(), "method": resp.GetMethod(), "required_headers": resp.GetRequiredHeaders(), "expires_at": resp.GetExpiresAt()}})
}

// CompleteUpload POST /api/v1/knowledge-documents/:id/complete-upload
func (h *KnowledgeHandler) CompleteUpload(c *gin.Context) {
	id, _ := strconv.ParseUint(c.Param("id"), 10, 64)
	ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
	defer cancel()
	resp, err := h.client.CompleteUpload(ctx, &knowledgev1.CompleteUploadRequest{UserId: int64(middleware.CurrentUserID(c)), DocumentId: int64(id)})
	if err != nil {
		log.Printf("CompleteUpload gRPC 调用失败: %v", err)
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 1999, "message": "上传服务暂不可用"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "data": gin.H{"document_id": resp.GetDocumentId(), "status": resp.GetStatus(), "index_version": resp.GetIndexVersion()}})
}
