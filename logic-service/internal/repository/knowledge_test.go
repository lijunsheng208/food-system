package repository

import (
	"regexp"
	"testing"
	"time"
)

// TestNewULID 验证 Outbox 事件 ID 满足数据库声明的标准 ULID 形状。
func TestNewULID(t *testing.T) {
	id, err := newULID(time.Date(2026, time.August, 29, 2, 30, 0, 0, time.UTC))
	if err != nil {
		t.Fatalf("生成 ULID 失败: %v", err)
	}
	if !regexp.MustCompile(`^[0-7][0-9ABCDEFGHJKMNPQRSTVWXYZ]{25}$`).MatchString(id) {
		t.Fatalf("ULID 格式无效: %q", id)
	}
}
