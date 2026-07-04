package oss

import (
	"fmt"
	"mime/multipart"
	"path/filepath"
	"time"

	alioss "github.com/aliyun/aliyun-oss-go-sdk/oss"
)

// Client OSS 客户端封装
type Client struct {
	bucket *alioss.Bucket
	config Config
}

// Config OSS 配置
type Config struct {
	Endpoint        string
	AccessKeyID     string
	AccessKeySecret string
	BucketName      string
	CustomDomain    string // 可选：CDN 或自定义域名，为空则使用 OSS 默认域名
}

// NewClient 创建 OSS 客户端
func NewClient(cfg Config) (*Client, error) {
	client, err := alioss.New(cfg.Endpoint, cfg.AccessKeyID, cfg.AccessKeySecret)
	if err != nil {
		return nil, fmt.Errorf("创建 OSS 客户端失败: %w", err)
	}

	bucket, err := client.Bucket(cfg.BucketName)
	if err != nil {
		return nil, fmt.Errorf("获取 Bucket 失败: %w", err)
	}

	return &Client{bucket: bucket, config: cfg}, nil
}

// Upload 上传文件，返回可访问的完整 URL
func (c *Client) Upload(key string, file multipart.File) (string, error) {
	if err := c.bucket.PutObject(key, file); err != nil {
		return "", fmt.Errorf("上传 OSS 失败: %w", err)
	}

	return c.publicURL(key), nil
}

// UploadAvatar 上传用户头像，自动生成 key
func (c *Client) UploadAvatar(userID uint64, ext string, file multipart.File) (string, error) {
	key := fmt.Sprintf("avatars/user_%d_%s%s", userID, time.Now().Format("20060102150405"), ext)
	return c.Upload(key, file)
}

// publicURL 根据配置生成可访问 URL
func (c *Client) publicURL(key string) string {
	if c.config.CustomDomain != "" {
		return fmt.Sprintf("https://%s/%s", c.config.CustomDomain, key)
	}
	return fmt.Sprintf("https://%s.%s/%s", c.config.BucketName, c.config.Endpoint, key)
}

// ExtByContentType 根据 content type 推断扩展名
func ExtByContentType(filename string) string {
	ext := filepath.Ext(filename)
	switch ext {
	case ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp":
		return ext
	default:
		return ".jpg"
	}
}
