package tools

import (
	"context"
	"fmt"

	"github.com/cloudwego/eino/components/tool"
	toolutils "github.com/cloudwego/eino/components/tool/utils"
	"github.com/lijunsheng/familyos/agent-service/internal/agent/citation"
	authv1 "github.com/lijunsheng/familyos/proto/gen/auth/v1"
)

// DietaryPreferencesProvider 提供当前用户个人饮食偏好的只读查询能力。
type DietaryPreferencesProvider interface {
	ListDietaryPreferences(context.Context, uint64) ([]*authv1.DietaryPreferenceInfo, error)
}

type dietaryPreferenceOutput struct {
	Preferences []*authv1.DietaryPreferenceInfo `json:"preferences"`
}

// NewDietaryPreferences 创建查询当前用户饮食习惯的 ReAct Tool。
func NewDietaryPreferences(provider DietaryPreferencesProvider, userID uint64) (tool.InvokableTool, error) {
	return newDietaryPreferences(provider, userID, nil)
}

// NewDietaryPreferencesWithCitations 创建会同步记录饮食偏好证据的 ReAct Tool。
func NewDietaryPreferencesWithCitations(provider DietaryPreferencesProvider, userID uint64, citations *citation.Store) (tool.InvokableTool, error) {
	return newDietaryPreferences(provider, userID, citations)
}

// newDietaryPreferences 统一构造饮食偏好查询 Tool，并绑定当前用户身份。
func newDietaryPreferences(provider DietaryPreferencesProvider, userID uint64, citations *citation.Store) (tool.InvokableTool, error) {
	if provider == nil || userID == 0 {
		return nil, fmt.Errorf("饮食偏好 Tool 配置无效")
	}
	return toolutils.InferTool("get_user_dietary_preferences", "查询当前用户已保存的饮食偏好、忌口和过敏信息。", func(ctx context.Context, _ struct{}) (dietaryPreferenceOutput, error) {
		preferences, err := provider.ListDietaryPreferences(ctx, userID)
		if err != nil {
			return dietaryPreferenceOutput{}, err
		}
		if citations != nil {
			content := "当前用户暂无已保存的饮食偏好。"
			if len(preferences) > 0 {
				content = "当前用户饮食偏好："
				for _, preference := range preferences {
					if preference != nil {
						content += fmt.Sprintf(" 类型%d=%s", preference.GetPreferenceType(), preference.GetPreferenceValue())
					}
				}
			}
			citations.Add(citation.Citation{ID: "C-dietary", ChunkID: fmt.Sprintf("dietary-preferences:%d", userID), DocumentName: "当前用户饮食偏好", Content: content})
		}
		return dietaryPreferenceOutput{Preferences: preferences}, nil
	})
}
