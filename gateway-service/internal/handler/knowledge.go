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

// ListKnowledgeDocuments 查询当前用户个人知识库中的文档列表。
func (h *KnowledgeHandler) ListKnowledgeDocuments(c *gin.Context) {
	baseID, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || baseID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 4001, "message": "知识库ID无效"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.ListKnowledgeDocuments(ctx, &knowledgev1.ListKnowledgeDocumentsRequest{UserId: int64(middleware.CurrentUserID(c)), KnowledgeBaseId: baseID})
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 1999, "message": "知识库服务暂不可用"})
		return
	}
	documents := make([]gin.H, 0, len(resp.GetDocuments()))
	for _, doc := range resp.GetDocuments() {
		documents = append(documents, gin.H{"document_id": doc.GetDocumentId(), "filename": doc.GetFilename(), "file_size": doc.GetFileSize(), "status": doc.GetStatus(), "index_version": doc.GetIndexVersion(), "created_at": doc.GetCreatedAt()})
	}
	c.JSON(http.StatusOK, gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "data": gin.H{"documents": documents}})
}

// GetDocumentViewTicket 获取当前用户可访问文档的短期查看地址。
func (h *KnowledgeHandler) GetDocumentViewTicket(c *gin.Context) {
	documentID, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || documentID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 4001, "message": "文档ID无效"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.GetDocumentViewTicket(ctx, &knowledgev1.GetDocumentViewTicketRequest{UserId: int64(middleware.CurrentUserID(c)), DocumentId: documentID})
	if err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 1999, "message": "知识库服务暂不可用"})
		return
	}
	status := http.StatusOK
	if resp.GetCode() == 4003 {
		status = http.StatusForbidden
	}
	if resp.GetCode() == 4004 {
		status = http.StatusNotFound
	}
	c.JSON(status, gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "data": gin.H{"document_id": resp.GetDocumentId(), "view_url": resp.GetViewUrl(), "filename": resp.GetFilename(), "content_type": resp.GetContentType(), "expires_at": resp.GetExpiresAt()}})
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

// DeleteDocument DELETE /api/v1/knowledge-documents/:id 请求删除文档及其所有索引版本。
func (h *KnowledgeHandler) DeleteDocument(c *gin.Context) {
	id, err := strconv.ParseUint(c.Param("id"), 10, 64)
	if err != nil || id == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "文档ID无效"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
	defer cancel()
	resp, err := h.client.DeleteDocument(ctx, &knowledgev1.DeleteDocumentRequest{UserId: int64(middleware.CurrentUserID(c)), DocumentId: int64(id)})
	if err != nil {
		log.Printf("DeleteDocument gRPC 调用失败: %v", err)
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 1999, "message": "知识库服务暂不可用"})
		return
	}
	status := http.StatusOK
	if resp.GetCode() == 4003 {
		status = http.StatusForbidden
	}
	if resp.GetCode() == 4004 {
		status = http.StatusNotFound
	}
	c.JSON(status, gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "data": gin.H{"document_id": resp.GetDocumentId(), "status": resp.GetStatus()}})
}

// DocumentStatusEvents 通过 SSE 推送文档处理状态，状态终结后关闭连接。
func (h *KnowledgeHandler) DocumentStatusEvents(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		c.Status(http.StatusBadRequest)
		return
	}
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("X-Accel-Buffering", "no")
	ctx := c.Request.Context()
	var last int32 = -1
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		callCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		resp, callErr := h.client.GetDocumentStatus(callCtx, &knowledgev1.GetDocumentStatusRequest{UserId: int64(middleware.CurrentUserID(c)), DocumentId: id})
		cancel()
		if callErr != nil {
			return
		}
		if resp.GetCode() != 0 {
			return
		}
		if resp.GetStatus() != last {
			last = resp.GetStatus()
			c.SSEvent("document.status", gin.H{"document_id": id, "status": resp.GetStatus(), "index_version": resp.GetIndexVersion()})
			c.Writer.Flush()
			if resp.GetStatus() == 3 || resp.GetStatus() == 4 || resp.GetStatus() == 6 {
				return
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
