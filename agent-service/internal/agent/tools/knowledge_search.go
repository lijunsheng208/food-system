package tools

import (
	"context"
	"fmt"

	"github.com/cloudwego/eino/components/tool"
	toolutils "github.com/cloudwego/eino/components/tool/utils"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/citation"
	"github.com/lijunsheng/familyos/agent-service/internal/rag/document"
)

// KnowledgeSearcher 描述知识库 Tool 依赖的混合检索能力。
type KnowledgeSearcher interface {
	Search(context.Context, string, document.SearchFilter) ([]document.SearchResult, error)
}

type knowledgeSearchInput struct {
	Query string `json:"query" jsonschema:"description=需要在当前知识库检索的完整问题,required"`
}

type knowledgeSearchOutput struct {
	Results []citation.Citation `json:"results"`
}

// NewKnowledgeSearch 创建请求级检索 Tool，知识库权限由服务端闭包注入而非模型参数决定。
func NewKnowledgeSearch(searcher KnowledgeSearcher, knowledgeBaseID uint64, topK int, citations *citation.Store) (tool.InvokableTool, error) {
	if searcher == nil || knowledgeBaseID == 0 || topK <= 0 || topK > 50 || citations == nil {
		return nil, fmt.Errorf("知识库检索 Tool 配置无效")
	}
	return toolutils.InferTool("search_knowledge_base", "检索当前用户已经授权的家庭知识库。回答菜谱、饮食、文档事实前必须调用。", func(ctx context.Context, input knowledgeSearchInput) (knowledgeSearchOutput, error) {
		results, err := searcher.Search(ctx, input.Query, document.SearchFilter{KnowledgeBaseID: knowledgeBaseID, Limit: topK})
		if err != nil {
			return knowledgeSearchOutput{}, err
		}
		output := knowledgeSearchOutput{Results: make([]citation.Citation, len(results))}
		for index, result := range results {
			output.Results[index] = citation.Citation{ID: fmt.Sprintf("C%d", index+1), ChunkID: result.ID, DocumentID: result.DocumentID, Content: result.Content}
		}
		citations.Replace(output.Results)
		return output, nil
	})
}
