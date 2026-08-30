package handler

import (
	"context"
	"io"
	"log"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/lijunsheng/familyos/gateway-service/internal/middleware"
	agentv1 "github.com/lijunsheng/familyos/proto/gen/agent/v1"
	knowledgev1 "github.com/lijunsheng/familyos/proto/gen/knowledge/v1"
	"google.golang.org/grpc"
)

// AgentChatHandler 校验知识库权限并将 Agent gRPC 流转换为 SSE。
type AgentChatHandler struct {
	agent     agentv1.AgentChatServiceClient
	knowledge knowledgev1.KnowledgeServiceClient
}

// NewAgentChatHandler 创建 Agent SSE 处理器。
func NewAgentChatHandler(agentConn, logicConn *grpc.ClientConn) *AgentChatHandler {
	return &AgentChatHandler{agent: agentv1.NewAgentChatServiceClient(agentConn), knowledge: knowledgev1.NewKnowledgeServiceClient(logicConn)}
}

// ChatStream 处理单轮问答并在客户端断开时取消下游模型和检索请求。
func (h *AgentChatHandler) ChatStream(c *gin.Context) {
	var body struct {
		KnowledgeBaseID int64  `json:"knowledge_base_id" binding:"required"`
		ConversationID  string `json:"conversation_id"`
		Message         string `json:"message" binding:"required"`
	}
	if c.ShouldBindJSON(&body) != nil || body.KnowledgeBaseID <= 0 || body.Message == "" {
		log.Printf("Agent SSE 请求参数无效: path=%s", c.Request.URL.Path)
		c.JSON(http.StatusBadRequest, gin.H{"code": 4001, "message": "问答请求无效"})
		return
	}
	userID := int64(middleware.CurrentUserID(c))
	verifyCtx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	verification, err := h.knowledge.EnsurePersonalKnowledgeBase(verifyCtx, &knowledgev1.EnsurePersonalKnowledgeBaseRequest{UserId: userID})
	cancel()
	if err != nil {
		log.Printf("Agent SSE 知识库校验失败: user_id=%d knowledge_base_id=%d err=%v", userID, body.KnowledgeBaseID, err)
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 1999, "message": "知识库服务暂不可用"})
		return
	}
	if verification.GetCode() != 0 || verification.GetKnowledgeBaseId() != body.KnowledgeBaseID {
		c.JSON(http.StatusForbidden, gin.H{"code": 4003, "message": "无权访问该知识库"})
		return
	}
	requestID := uuid.NewString()
	ctx, cancel := context.WithTimeout(c.Request.Context(), 90*time.Second)
	defer cancel()
	stream, err := h.agent.ChatStream(ctx, &agentv1.ChatStreamRequest{UserId: userID, KnowledgeBaseId: body.KnowledgeBaseID, ConversationId: body.ConversationID, Message: body.Message, RequestId: requestID})
	if err != nil {
		log.Printf("Agent SSE 连接 gRPC 失败: request_id=%q err=%v", requestID, err)
		c.JSON(http.StatusServiceUnavailable, gin.H{"code": 1999, "message": "Agent 服务暂不可用"})
		return
	}
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	c.Header("X-Accel-Buffering", "no")
	c.SSEvent("metadata", gin.H{"request_id": requestID})
	c.Writer.Flush()
	for {
		event, receiveErr := stream.Recv()
		if receiveErr == io.EOF {
			log.Printf("Agent SSE 正常结束: request_id=%q", requestID)
			return
		}
		if receiveErr != nil {
			log.Printf("Agent SSE 接收 gRPC 事件失败: request_id=%q err=%v", requestID, receiveErr)
			c.SSEvent("error", gin.H{"request_id": requestID, "message": "问答生成失败"})
			c.Writer.Flush()
			return
		}
		payload := gin.H{"request_id": event.GetRequestId(), "content": event.GetContent()}
		if citation := event.GetCitation(); citation != nil {
			payload["citation"] = gin.H{"citation_id": citation.GetCitationId(), "chunk_id": citation.GetChunkId(), "document_id": citation.GetDocumentId(), "content": citation.GetContent()}
		}
		c.SSEvent(event.GetType(), payload)
		c.Writer.Flush()
	}
}
