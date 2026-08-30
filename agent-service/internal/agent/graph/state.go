package graph

// State 保存一次无持久化问答在 Query Rewrite 和 ReAct 之间传递的数据。
type State struct {
	UserID          uint64
	KnowledgeBaseID uint64
	ConversationID  string
	OriginalQuery   string
	RewrittenQuery  string
}
