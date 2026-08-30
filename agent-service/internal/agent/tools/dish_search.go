package tools

import (
	"context"
	"fmt"
	"strings"

	"github.com/cloudwego/eino/components/tool"
	toolutils "github.com/cloudwego/eino/components/tool/utils"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/citation"
	dishv1 "github.com/lijunsheng/familyos/proto/gen/dish/v1"
)

// DishSearcher 提供系统菜谱的关键字搜索能力。
type DishSearcher interface {
	SearchDishes(context.Context, string) ([]*dishv1.DishInfo, error)
}

type dishSearchInput struct {
	Keyword string `json:"keyword" jsonschema:"description=要搜索的菜谱名称或关键字,required"`
}

type dishSearchOutput struct {
	Dishes []*dishv1.DishInfo `json:"dishes"`
}

// NewDishSearch 创建搜索系统菜谱的 ReAct Tool。
func NewDishSearch(searcher DishSearcher) (tool.InvokableTool, error) {
	return newDishSearch(searcher, nil)
}

// NewDishSearchWithCitations 创建会同步记录菜谱搜索证据的 ReAct Tool。
func NewDishSearchWithCitations(searcher DishSearcher, citations *citation.Store) (tool.InvokableTool, error) {
	return newDishSearch(searcher, citations)
}

// newDishSearch 统一构造菜谱关键字搜索 Tool。
func newDishSearch(searcher DishSearcher, citations *citation.Store) (tool.InvokableTool, error) {
	if searcher == nil {
		return nil, fmt.Errorf("菜谱搜索 Tool 配置无效")
	}
	return toolutils.InferTool("search_recipes", "按关键字搜索 FamilyOS 当前菜谱库中的菜谱。需要菜谱名称或菜谱内容时调用。", func(ctx context.Context, input dishSearchInput) (dishSearchOutput, error) {
		if strings.TrimSpace(input.Keyword) == "" {
			return dishSearchOutput{}, fmt.Errorf("菜谱搜索关键字不能为空")
		}
		dishes, err := searcher.SearchDishes(ctx, strings.TrimSpace(input.Keyword))
		if err != nil {
			return dishSearchOutput{}, err
		}
		if citations != nil {
			for _, dish := range dishes {
				if dish == nil {
					continue
				}
				content := dish.GetDescription()
				if content == "" {
					content = dish.GetName()
				}
				citations.Add(citation.Citation{ID: fmt.Sprintf("C-dish-%d", dish.GetId()), ChunkID: fmt.Sprintf("dish:%d", dish.GetId()), DocumentName: dish.GetName(), Content: content})
			}
		}
		return dishSearchOutput{Dishes: dishes}, nil
	})
}
