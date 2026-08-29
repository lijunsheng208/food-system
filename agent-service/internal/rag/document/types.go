package document

// SourceDocument 描述从 Logic 下载、等待解析的原始文档。
type SourceDocument struct {
	DocumentID      uint64
	KnowledgeBaseID uint64
	UserID          uint64
	IndexVersion    uint
	Filename        string
	Extension       string
	ContentType     string
	Content         []byte
}

// ParsedDocument 是 Parser 输出的规范化文本。
type ParsedDocument struct {
	Text     string
	Metadata map[string]any
}

// Chunk 是尚未生成向量的文档切片。
type Chunk struct {
	ID              string
	DocumentID      uint64
	KnowledgeBaseID uint64
	UserID          uint64
	IndexVersion    uint
	Index           int
	Content         string
	ContentSHA256   string
	Metadata        map[string]any
}

// EmbeddedChunk 是带有向量的文档切片。
type EmbeddedChunk struct {
	Chunk
	Embedding []float32
}

// SearchFilter 限定检索范围，知识库 ID 是必填的权限边界。
type SearchFilter struct {
	KnowledgeBaseID uint64
	DocumentID      uint64
	Limit           int
}

// SearchResult 描述一次向量检索命中的切片及相似度。
type SearchResult struct {
	Chunk
	Score float32
}
