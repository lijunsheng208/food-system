package parser

import (
	"fmt"
	"path/filepath"
	"strings"
)

// Registry 按小写扩展名保存文档解析器。
type Registry struct{ parsers map[string]Parser }

// NewRegistry 创建仅包含 FamilyOS 当前允许格式的解析器注册表。
func NewRegistry() *Registry {
	r := &Registry{parsers: make(map[string]Parser)}
	r.Register([]string{".txt"}, Text{})
	r.Register([]string{".md", ".markdown"}, Markdown{})
	r.Register([]string{".pdf"}, PDF{})
	r.Register([]string{".docx"}, DOCX{})
	return r
}

// Register 为一个或多个扩展名注册解析器。
func (r *Registry) Register(extensions []string, value Parser) {
	for _, extension := range extensions {
		extension = strings.ToLower(strings.TrimSpace(extension))
		if extension != "" && !strings.HasPrefix(extension, ".") {
			extension = "." + extension
		}
		if extension != "" {
			r.parsers[extension] = value
		}
	}
}

// Resolve 根据显式扩展名或文件名选择解析器。
func (r *Registry) Resolve(extension, filename string) (Parser, error) {
	extension = strings.ToLower(strings.TrimSpace(extension))
	if extension == "" {
		extension = strings.ToLower(filepath.Ext(filename))
	}
	if extension != "" && !strings.HasPrefix(extension, ".") {
		extension = "." + extension
	}
	value, ok := r.parsers[extension]
	if !ok {
		return nil, fmt.Errorf("不支持的文档格式: %s", extension)
	}
	return value, nil
}
