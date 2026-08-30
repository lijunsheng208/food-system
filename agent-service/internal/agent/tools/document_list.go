package tools

import "context"

// DocumentListProvider 定义后续按可信用户身份查询知识库文档列表的只读边界。
type DocumentListProvider interface {
	ListDocuments(context.Context, uint64, uint64) (any, error)
}
