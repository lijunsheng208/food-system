package graph

import "github.com/cloudwego/eino/schema"

// State 保存一次问答的会话历史、原始问题和改写结果。
type State struct {
	UserID          uint64
	KnowledgeBaseID uint64
	ConversationID  string
	OriginalQuery   string
	RewrittenQuery  string
	History         []*schema.Message
}
