package rewrite

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/compose"
	"github.com/cloudwego/eino/schema"
)

type result struct {
	Query string `json:"standalone_query"`
}

// Input 包含当前问题和用于指代消解的最近对话历史。
type Input struct {
	Query   string
	History []*schema.Message
}

// NewNode 创建并编译实际的 Eino Query Rewrite Graph Node。
func NewNode(chatModel model.BaseChatModel) (compose.Runnable[Input, string], error) {
	if chatModel == nil {
		return nil, fmt.Errorf("Query Rewrite 模型不能为空")
	}
	graph := compose.NewGraph[Input, string]()
	if err := graph.AddLambdaNode("query_rewrite", compose.InvokableLambda(func(ctx context.Context, input Input) (string, error) {
		return generate(ctx, chatModel, input)
	})); err != nil {
		return nil, fmt.Errorf("添加 Query Rewrite Node 失败: %w", err)
	}
	if err := graph.AddEdge(compose.START, "query_rewrite"); err != nil {
		return nil, err
	}
	if err := graph.AddEdge("query_rewrite", compose.END); err != nil {
		return nil, err
	}
	runnable, err := graph.Compile(context.Background())
	if err != nil {
		return nil, fmt.Errorf("编译 Query Rewrite Graph 失败: %w", err)
	}
	return runnable, nil
}

// generate 调用 ChatModel 并严格解析 Query Rewrite 的结构化输出。
func generate(ctx context.Context, chatModel model.BaseChatModel, input Input) (string, error) {
	messages := make([]*schema.Message, 0, len(input.History)+2)
	messages = append(messages, schema.SystemMessage(systemPrompt))
	messages = append(messages, input.History...)
	messages = append(messages, schema.UserMessage(input.Query))
	response, err := chatModel.Generate(ctx, messages)
	if err != nil {
		return "", fmt.Errorf("查询改写失败: %w", err)
	}
	content := strings.TrimSuffix(strings.TrimPrefix(strings.TrimSpace(response.Content), "```json"), "```")
	var decoded result
	if err := json.Unmarshal([]byte(strings.TrimSpace(content)), &decoded); err != nil || strings.TrimSpace(decoded.Query) == "" {
		return "", fmt.Errorf("查询改写返回格式无效")
	}
	return strings.TrimSpace(decoded.Query), nil
}
