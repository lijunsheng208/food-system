package tools

import "context"

// DocumentStatusProvider 定义后续查询当前用户文档索引状态的只读边界。
type DocumentStatusProvider interface {
	GetDocumentStatus(context.Context, uint64, uint64) (any, error)
}
