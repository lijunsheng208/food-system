package react

import (
	"context"
	"fmt"

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/components/tool"
	"github.com/cloudwego/eino/compose"
	einoreact "github.com/cloudwego/eino/flow/agent/react"
)

// NewAgent 使用请求级 Tool 集合创建 CloudWeGo Eino ReAct Agent。
func NewAgent(ctx context.Context, chatModel model.ToolCallingChatModel, tools []tool.BaseTool, maxSteps int) (*einoreact.Agent, error) {
	if chatModel == nil || len(tools) == 0 || maxSteps <= 0 {
		return nil, fmt.Errorf("ReAct Agent 配置无效")
	}
	agent, err := einoreact.NewAgent(ctx, &einoreact.AgentConfig{
		ToolCallingModel: chatModel,
		ToolsConfig:      compose.ToolsNodeConfig{Tools: tools},
		MaxStep:          maxSteps,
		MessageModifier:  einoreact.NewPersonaModifier(systemPrompt),
	})
	if err != nil {
		return nil, fmt.Errorf("创建 Eino ReAct Agent 失败: %w", err)
	}
	return agent, nil
}
