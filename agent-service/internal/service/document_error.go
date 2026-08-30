package service

import (
	"errors"
	"regexp"
	"strings"
)

var sensitiveURLPattern = regexp.MustCompile(`https?://[^\s]+`)
var bearerTokenPattern = regexp.MustCompile(`(?i)bearer\s+[a-z0-9._~+/-]+`)

// PermanentDocumentError 表示重试无法恢复的文档处理错误。
type PermanentDocumentError struct {
	Code    string
	Message string
	Cause   error
}

// Error 返回不包含底层敏感上下文的稳定错误描述。
func (e *PermanentDocumentError) Error() string { return e.Message }

// Unwrap 返回底层错误供内部错误链判断。
func (e *PermanentDocumentError) Unwrap() error { return e.Cause }

// NewPermanentDocumentError 创建带稳定错误码的不可重试错误。
func NewPermanentDocumentError(code, message string, cause error) error {
	return &PermanentDocumentError{Code: code, Message: message, Cause: cause}
}

// DocumentFailure 提取可安全写入 Logic 的失败代码和用户可读信息。
func DocumentFailure(err error, attempts, maxAttempts uint) (string, string) {
	var permanent *PermanentDocumentError
	if errors.As(err, &permanent) {
		return permanent.Code, permanent.Message
	}
	if attempts >= maxAttempts {
		return "RETRY_EXHAUSTED", "文档处理多次失败，请稍后手动重新处理"
	}
	return "", ""
}

// SanitizeTaskError 清理任务错误中的临时 URL 和认证信息，并限制持久化长度。
func SanitizeTaskError(err error) string {
	if err == nil {
		return ""
	}
	message := sensitiveURLPattern.ReplaceAllString(err.Error(), "[REDACTED_URL]")
	message = bearerTokenPattern.ReplaceAllString(message, "Bearer [REDACTED]")
	message = strings.TrimSpace(message)
	if len(message) > 500 {
		message = message[:500]
	}
	return message
}
