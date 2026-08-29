package service

import (
	"strings"
	"testing"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/pkg/oss"
)

// TestValidateUploadMetadata 验证上传对象各校验项能返回明确的内部失败上下文。
func TestValidateUploadMetadata(t *testing.T) {
	sha256 := strings.Repeat("a", 64)
	doc := &model.KnowledgeDocument{ID: 42}
	session := &model.KnowledgeUploadSession{ID: "session-1", DeclaredFileSize: 128, DeclaredMimeType: "application/pdf", DeclaredSHA256: &sha256}
	valid := func() *oss.ObjectMetadata {
		return &oss.ObjectMetadata{ContentLength: 128, ContentType: "application/pdf", Metadata: map[string]string{"document-id": "42", "upload-session-id": "session-1", "sha256": sha256}}
	}

	tests := []struct {
		name      string
		mutate    func(*oss.ObjectMetadata)
		wantField string
	}{
		{name: "文件大小", mutate: func(meta *oss.ObjectMetadata) { meta.ContentLength = 127 }, wantField: "field=content_length"},
		{name: "文件类型", mutate: func(meta *oss.ObjectMetadata) { meta.ContentType = "text/plain" }, wantField: "field=content_type"},
		{name: "文档ID", mutate: func(meta *oss.ObjectMetadata) { meta.Metadata["document-id"] = "41" }, wantField: "field=document-id"},
		{name: "上传会话", mutate: func(meta *oss.ObjectMetadata) { meta.Metadata["upload-session-id"] = "session-2" }, wantField: "field=upload-session-id"},
		{name: "文件摘要", mutate: func(meta *oss.ObjectMetadata) { meta.Metadata["sha256"] = strings.Repeat("b", 64) }, wantField: "field=sha256"},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			meta := valid()
			test.mutate(meta)
			if mismatch := validateUploadMetadata(meta, doc, session); !strings.Contains(mismatch, test.wantField) {
				t.Fatalf("校验结果 %q 不包含 %q", mismatch, test.wantField)
			}
		})
	}
	if mismatch := validateUploadMetadata(valid(), doc, session); mismatch != "" {
		t.Fatalf("有效元数据不应失败: %s", mismatch)
	}
}
