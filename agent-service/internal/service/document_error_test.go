package service

import (
	"errors"
	"strings"
	"testing"
)

// TestSanitizeTaskErrorRedactsSensitiveContext 验证任务错误不会持久化签名 URL 或 Bearer Token。
func TestSanitizeTaskErrorRedactsSensitiveContext(t *testing.T) {
	message := SanitizeTaskError(errors.New("GET https://oss.example/file?Signature=secret Authorization: Bearer token.value"))
	if strings.Contains(message, "Signature") || strings.Contains(message, "token.value") {
		t.Fatalf("错误信息未脱敏: %s", message)
	}
}

// TestDocumentFailureClassifiesTerminalErrors 验证永久错误和重试耗尽均生成稳定失败码。
func TestDocumentFailureClassifiesTerminalErrors(t *testing.T) {
	code, _ := DocumentFailure(NewPermanentDocumentError("DOCUMENT_EMPTY", "文档解析结果为空", nil), 1, 5)
	if code != "DOCUMENT_EMPTY" {
		t.Fatalf("永久错误码=%q", code)
	}
	code, _ = DocumentFailure(errors.New("timeout"), 5, 5)
	if code != "RETRY_EXHAUSTED" {
		t.Fatalf("重试耗尽错误码=%q", code)
	}
}
