package citation

import "sync"

// Citation 是一次问答中由真实检索结果生成的引用。
type Citation struct {
	ID           string `json:"citation_id"`
	ChunkID      string `json:"chunk_id"`
	DocumentID   uint64 `json:"document_id"`
	DocumentName string `json:"document_name"`
	Content      string `json:"content"`
}

// Store 以并发安全方式收集当前 ReAct 请求产生的真实引用。
type Store struct {
	mu    sync.RWMutex
	items []Citation
}

// Replace 使用本次工具结果替换引用，避免重复调用工具后混入过期候选。
func (s *Store) Replace(items []Citation) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.items = append([]Citation(nil), items...)
}

// Add 追加本轮 Tool 产生的引用，保留之前已经确认的检索证据。
func (s *Store) Add(items ...Citation) {
	if len(items) == 0 {
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.items = append(s.items, items...)
}

// List 返回引用快照，调用方不能修改 Store 内部切片。
func (s *Store) List() []Citation {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]Citation(nil), s.items...)
}

// HasEvidence 判断当前请求是否产生至少一条真实检索证据。
func (s *Store) HasEvidence() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.items) > 0
}
