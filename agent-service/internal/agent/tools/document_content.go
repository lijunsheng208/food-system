package tools

import "context"

// DocumentContentProvider 定义后续读取已授权文档正文片段的只读边界。
type DocumentContentProvider interface {
	GetDocumentContent(context.Context, uint64, uint64, uint64) (any, error)
}
