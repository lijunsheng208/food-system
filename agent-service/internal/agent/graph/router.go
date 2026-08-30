package graph

import "strings"

// validateInput 校验 Graph 的内部不变量，权限字段必须由上游可信上下文注入。
func validateInput(state State) bool {
	return state.UserID > 0 && state.KnowledgeBaseID > 0 && strings.TrimSpace(state.OriginalQuery) != ""
}
