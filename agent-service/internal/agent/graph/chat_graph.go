package graph

import (
	"context"
	"fmt"
	"io"
	"log"
	"strings"

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/components/tool"
	"github.com/cloudwego/eino/compose"
	"github.com/cloudwego/eino/schema"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/citation"
	reactflow "github.com/lijunsheng/familyos/agent-service/internal/agent/react"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/rewrite"
	agenttools "github.com/lijunsheng/familyos/agent-service/internal/agent/tools"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/transport"
)

// Config 描述 ReAct 步数和最终检索数量。
type Config struct {
	MaxSteps int
	TopK     int
}

// ChatGraph 组装 Query Rewrite Graph、ReAct Agent、引用校验和流输出。
type ChatGraph struct {
	model    model.ToolCallingChatModel
	searcher agenttools.KnowledgeSearcher
	rewriter compose.Runnable[string, string]
	config   Config
}

// NewChatGraph 创建并预编译 Query Rewrite 节点。
func NewChatGraph(rewriteModel model.BaseChatModel, chatModel model.ToolCallingChatModel, searcher agenttools.KnowledgeSearcher, config Config) (*ChatGraph, error) {
	if rewriteModel == nil || chatModel == nil || searcher == nil || config.MaxSteps <= 0 || config.TopK <= 0 || config.TopK > 50 {
		return nil, fmt.Errorf("Agent Chat Graph 配置无效")
	}
	rewriter, err := rewrite.NewNode(rewriteModel)
	if err != nil {
		return nil, err
	}
	return &ChatGraph{model: chatModel, searcher: searcher, rewriter: rewriter, config: config}, nil
}

// Stream 运行 Query Rewrite → ReAct，并仅释放具有真实引用支撑的模型回答。
func (g *ChatGraph) Stream(ctx context.Context, state State, emit transport.Emitter) error {
	if !validateInput(state) || emit == nil {
		return fmt.Errorf("问答请求无效")
	}
	rewritten, err := g.rewriter.Invoke(ctx, state.OriginalQuery)
	if err != nil {
		log.Printf("Agent Query Rewrite 失败: user_id=%d knowledge_base_id=%d err=%v", state.UserID, state.KnowledgeBaseID, err)
		return err
	}
	log.Printf("Agent Query Rewrite 完成: user_id=%d original_len=%d rewritten_len=%d output=%q", state.UserID, len(state.OriginalQuery), len(rewritten), rewritten)
	state.RewrittenQuery = rewritten
	citations := &citation.Store{}
	knowledgeTool, err := agenttools.NewKnowledgeSearch(g.searcher, state.KnowledgeBaseID, g.config.TopK, citations)
	if err != nil {
		log.Printf("Agent ReAct 创建失败: err=%v", err)
		return err
	}
	agent, err := reactflow.NewAgent(ctx, g.model, []tool.BaseTool{knowledgeTool}, g.config.MaxSteps)
	if err != nil {
		log.Printf("Agent ReAct 流启动失败: err=%v", err)
		return err
	}
	stream, err := agent.Stream(ctx, []*schema.Message{schema.UserMessage(state.RewrittenQuery)})
	if err != nil {
		return fmt.Errorf("启动 ReAct 流失败: %w", err)
	}
	defer stream.Close()
	var pending strings.Builder
	released := false
	for {
		message, receiveErr := stream.Recv()
		if receiveErr == io.EOF {
			break
		}
		if receiveErr != nil {
			log.Printf("Agent ReAct 流读取失败: err=%v", receiveErr)
			return fmt.Errorf("读取 ReAct 流失败: %w", receiveErr)
		}
		if message.Content == "" {
			continue
		}
		if !citations.HasEvidence() {
			pending.WriteString(message.Content)
			continue
		}
		if !released && pending.Len() > 0 {
			if err := emit(transport.StreamEvent{Type: "answer_delta", Content: pending.String()}); err != nil {
				return err
			}
			pending.Reset()
		}
		if err := emit(transport.StreamEvent{Type: "answer_delta", Content: message.Content}); err != nil {
			return err
		}
		released = true
	}
	items := citations.List()
	if len(items) == 0 {
		if err := emit(transport.StreamEvent{Type: "answer_delta", Content: "当前知识库中没有找到足够依据，暂时无法确认。"}); err != nil {
			return err
		}
		return emit(transport.StreamEvent{Type: "completed"})
	}
	if !released && pending.Len() > 0 {
		if err := emit(transport.StreamEvent{Type: "answer_delta", Content: pending.String()}); err != nil {
			return err
		}
	}
	for index := range items {
		value := items[index]
		if err := emit(transport.StreamEvent{Type: "citation", Citation: &value}); err != nil {
			return err
		}
	}
	return emit(transport.StreamEvent{Type: "completed"})
}
