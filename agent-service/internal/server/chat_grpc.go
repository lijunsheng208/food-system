package server

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/cloudwego/eino/schema"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/citation"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/graph"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/transport"
	"github.com/lijunsheng/familyos/agent-service/internal/model"
	"github.com/lijunsheng/familyos/agent-service/internal/repository"
	agentv1 "github.com/lijunsheng/familyos/proto/gen/agent/v1"
)

// ChatServer 将 Agent 问答事件转换为内部 gRPC 流。
type ChatServer struct {
	agentv1.UnimplementedAgentChatServiceServer
	chat           *graph.ChatGraph
	conversations  *repository.ConversationRepo
	recentMessages int
}

// NewChatServer 创建内部问答 gRPC 服务。
func NewChatServer(chat *graph.ChatGraph, conversations *repository.ConversationRepo, recentMessages int) (*ChatServer, error) {
	if chat == nil || conversations == nil || recentMessages <= 0 {
		return nil, fmt.Errorf("Agent 问答服务不能为空")
	}
	return &ChatServer{chat: chat, conversations: conversations, recentMessages: recentMessages}, nil
}

// CreateConversation 创建归属于当前用户和知识库的多轮会话。
func (s *ChatServer) CreateConversation(ctx context.Context, request *agentv1.CreateConversationRequest) (*agentv1.CreateConversationResponse, error) {
	if request.GetUserId() <= 0 || request.GetKnowledgeBaseId() <= 0 {
		return nil, fmt.Errorf("创建会话请求无效")
	}
	value, err := s.conversations.Create(ctx, uint64(request.GetUserId()), uint64(request.GetKnowledgeBaseId()))
	if err != nil {
		return nil, err
	}
	log.Printf("Agent 会话已创建: conversation_id=%q user_id=%d knowledge_base_id=%d", value.ID, value.UserID, value.KnowledgeBaseID)
	return &agentv1.CreateConversationResponse{ConversationId: value.ID}, nil
}

// ChatStream 校验内部请求并持续发送回答、引用和完成事件。
func (s *ChatServer) ChatStream(request *agentv1.ChatStreamRequest, stream agentv1.AgentChatService_ChatStreamServer) error {
	log.Printf("Agent ChatStream 收到请求: request_id=%q user_id=%d knowledge_base_id=%d message_len=%d", request.GetRequestId(), request.GetUserId(), request.GetKnowledgeBaseId(), len(request.GetMessage()))
	if request.GetUserId() <= 0 || request.GetKnowledgeBaseId() <= 0 || request.GetConversationId() == "" || request.GetMessage() == "" || request.GetRequestId() == "" {
		log.Printf("Agent ChatStream 请求校验失败: request_id=%q", request.GetRequestId())
		return fmt.Errorf("问答请求无效")
	}
	if err := s.conversations.BeginTurn(stream.Context(), request.GetConversationId(), request.GetRequestId(), uint64(request.GetUserId()), uint64(request.GetKnowledgeBaseId()), request.GetMessage()); err != nil {
		return err
	}
	history, err := s.conversations.RecentHistory(stream.Context(), request.GetConversationId(), request.GetRequestId(), s.recentMessages)
	if err != nil {
		persistCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if persistErr := s.conversations.FailAssistant(persistCtx, request.GetRequestId(), false, err); persistErr != nil {
			log.Printf("Agent 助手失败状态保存失败: request_id=%q err=%v", request.GetRequestId(), persistErr)
		}
		return err
	}
	messages := make([]*schema.Message, 0, len(history))
	for _, item := range history {
		if item.Role == model.MessageRoleUser {
			messages = append(messages, schema.UserMessage(item.Content))
		} else if item.Role == model.MessageRoleAssistant {
			messages = append(messages, schema.AssistantMessage(item.Content, nil))
		}
	}
	state := graph.State{UserID: uint64(request.GetUserId()), KnowledgeBaseID: uint64(request.GetKnowledgeBaseId()), ConversationID: request.GetConversationId(), OriginalQuery: request.GetMessage(), History: messages}
	var answer strings.Builder
	citations := make([]citation.Citation, 0)
	err = s.chat.Stream(stream.Context(), state, func(event transport.StreamEvent) error {
		log.Printf("Agent ChatStream 发送事件: request_id=%q type=%s content_len=%d citation=%t", request.GetRequestId(), event.Type, len(event.Content), event.Citation != nil)
		response := &agentv1.ChatStreamEvent{Type: event.Type, RequestId: request.GetRequestId(), Content: event.Content}
		if event.Citation != nil {
			citations = append(citations, *event.Citation)
			response.Citation = &agentv1.ChatCitation{CitationId: event.Citation.ID, ChunkId: event.Citation.ChunkID, DocumentId: int64(event.Citation.DocumentID), DocumentName: event.Citation.DocumentName, Content: event.Citation.Content}
		}
		if event.Type == "answer_delta" {
			answer.WriteString(event.Content)
		}
		if event.Type == "completed" {
			if err := s.conversations.CompleteAssistant(stream.Context(), request.GetRequestId(), answer.String(), citations); err != nil {
				return err
			}
		}
		return stream.Send(response)
	})
	if err != nil {
		log.Printf("Agent ChatStream 处理失败: request_id=%q err=%v", request.GetRequestId(), err)
		persistCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if persistErr := s.conversations.FailAssistant(persistCtx, request.GetRequestId(), stream.Context().Err() != nil, err); persistErr != nil {
			log.Printf("Agent 助手失败状态保存失败: request_id=%q err=%v", request.GetRequestId(), persistErr)
		}
	}
	return err
}
