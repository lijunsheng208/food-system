package server

import (
	"fmt"
	"log"

	"github.com/lijunsheng/familyos/agent-service/internal/agent/graph"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/transport"
	agentv1 "github.com/lijunsheng/familyos/proto/gen/agent/v1"
)

// ChatServer 将 Agent 问答事件转换为内部 gRPC 流。
type ChatServer struct {
	agentv1.UnimplementedAgentChatServiceServer
	chat *graph.ChatGraph
}

// NewChatServer 创建内部问答 gRPC 服务。
func NewChatServer(chat *graph.ChatGraph) (*ChatServer, error) {
	if chat == nil {
		return nil, fmt.Errorf("Agent 问答服务不能为空")
	}
	return &ChatServer{chat: chat}, nil
}

// ChatStream 校验内部请求并持续发送回答、引用和完成事件。
func (s *ChatServer) ChatStream(request *agentv1.ChatStreamRequest, stream agentv1.AgentChatService_ChatStreamServer) error {
	log.Printf("Agent ChatStream 收到请求: request_id=%q user_id=%d knowledge_base_id=%d message_len=%d", request.GetRequestId(), request.GetUserId(), request.GetKnowledgeBaseId(), len(request.GetMessage()))
	if request.GetUserId() <= 0 || request.GetKnowledgeBaseId() <= 0 || request.GetMessage() == "" || request.GetRequestId() == "" {
		log.Printf("Agent ChatStream 请求校验失败: request_id=%q", request.GetRequestId())
		return fmt.Errorf("问答请求无效")
	}
	state := graph.State{UserID: uint64(request.GetUserId()), KnowledgeBaseID: uint64(request.GetKnowledgeBaseId()), ConversationID: request.GetConversationId(), OriginalQuery: request.GetMessage()}
	err := s.chat.Stream(stream.Context(), state, func(event transport.StreamEvent) error {
		log.Printf("Agent ChatStream 发送事件: request_id=%q type=%s content_len=%d citation=%t", request.GetRequestId(), event.Type, len(event.Content), event.Citation != nil)
		response := &agentv1.ChatStreamEvent{Type: event.Type, RequestId: request.GetRequestId(), Content: event.Content}
		if event.Citation != nil {
			response.Citation = &agentv1.ChatCitation{CitationId: event.Citation.ID, ChunkId: event.Citation.ChunkID, DocumentId: int64(event.Citation.DocumentID), Content: event.Citation.Content}
		}
		return stream.Send(response)
	})
	if err != nil {
		log.Printf("Agent ChatStream 处理失败: request_id=%q err=%v", request.GetRequestId(), err)
	}
	return err
}
