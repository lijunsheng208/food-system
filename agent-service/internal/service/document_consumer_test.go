package service

import "testing"

// TestParseDocumentIndexEvent 验证能解析 Logic Publisher 发送的 INDEX 消息。
func TestParseDocumentIndexEvent(t *testing.T) {
	body := []byte(`{"schema_version":1,"event_id":"01JABCDEF0123456789ABCDEFGH","event_type":"document.index.requested","document_id":25,"user_id":1001,"knowledge_base_id":8,"index_version":1,"occurred_at":"2026-08-28T10:00:00+08:00"}`)
	event, err := parseDocumentIndexEvent(body)
	if err != nil {
		t.Fatalf("解析消息失败: %v", err)
	}
	if event.DocumentID != 25 || event.IndexVersion != 1 || event.EventID == "" {
		t.Fatalf("解析结果不正确: %+v", event)
	}
}

// TestParseDocumentIndexEventRejectsInvalidEvent 验证无效事件不会进入任务表。
func TestParseDocumentIndexEventRejectsInvalidEvent(t *testing.T) {
	_, err := parseDocumentIndexEvent([]byte(`{"schema_version":1,"event_type":"document.index.requested","document_id":25}`))
	if err == nil {
		t.Fatal("期望拒绝缺少必填字段的消息")
	}
}
