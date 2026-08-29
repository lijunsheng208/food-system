package oss

import (
	"net/http"
	"testing"
)

// TestExtractUserMetadataNormalizesKeys 验证 HTTP Header 规范化后仍以小写业务键读取元数据。
func TestExtractUserMetadataNormalizesKeys(t *testing.T) {
	header := http.Header{}
	header.Set("X-Oss-Meta-Document-Id", "42")
	header.Set("x-oss-meta-upload-session-id", "session-1")
	header.Set("X-OSS-META-SHA256", "digest")
	header.Set("Content-Type", "application/pdf")

	metadata := extractUserMetadata(header)
	if metadata["document-id"] != "42" {
		t.Fatalf("document-id = %q, want %q", metadata["document-id"], "42")
	}
	if metadata["upload-session-id"] != "session-1" {
		t.Fatalf("upload-session-id = %q, want %q", metadata["upload-session-id"], "session-1")
	}
	if metadata["sha256"] != "digest" {
		t.Fatalf("sha256 = %q, want %q", metadata["sha256"], "digest")
	}
	if _, exists := metadata["content-type"]; exists {
		t.Fatal("非 OSS 自定义元数据不应被提取")
	}
}
