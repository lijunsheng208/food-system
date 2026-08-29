package oss

import (
	"context"
	"fmt"
	"mime/multipart"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"
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

// PresignPutInput 描述预签名上传对象及其必须携带的请求头。
type PresignPutInput struct {
	Key         string
	ContentType string
	Metadata    map[string]string
	ExpiresIn   time.Duration
}

// PresignedPut 是移动端直传 OSS 所需的临时授权信息。
type PresignedPut struct {
	URL       string
	Headers   map[string]string
	ExpiresAt time.Time
}

// ObjectMetadata 是 OSS 对象校验所需的元数据。
type ObjectMetadata struct {
	ContentLength int64
	ContentType   string
	ETag          string
	Metadata      map[string]string
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

// PresignPut 生成限制对象 Key、类型和元数据的临时 PUT 地址。
func (c *Client) PresignPut(ctx context.Context, input PresignPutInput) (*PresignedPut, error) {
	if input.Key == "" || input.ContentType == "" || input.ExpiresIn <= 0 {
		return nil, fmt.Errorf("OSS 预签名参数无效")
	}
	options := []alioss.Option{alioss.ContentType(input.ContentType)}
	headers := map[string]string{"Content-Type": input.ContentType}
	for key, value := range input.Metadata {
		options = append(options, alioss.Meta(key, value))
		headers["x-oss-meta-"+key] = value
	}
	seconds := int64(input.ExpiresIn / time.Second)
	if seconds < 1 {
		seconds = 1
	}
	url, err := c.bucket.SignURL(input.Key, alioss.HTTPPut, seconds, options...)
	if err != nil {
		return nil, fmt.Errorf("生成 OSS 上传地址失败: %w", err)
	}
	return &PresignedPut{URL: url, Headers: headers, ExpiresAt: time.Now().Add(input.ExpiresIn)}, nil
}

// HeadObject 查询对象完整元数据，用于确认客户端直传结果及签名约束字段。
func (c *Client) HeadObject(ctx context.Context, key string) (*ObjectMetadata, error) {
	header, err := c.bucket.GetObjectDetailedMeta(key)
	if err != nil {
		return nil, fmt.Errorf("查询 OSS 对象失败: %w", err)
	}
	contentLength, err := strconv.ParseInt(header.Get("Content-Length"), 10, 64)
	if err != nil {
		return nil, fmt.Errorf("OSS 对象大小无效: %w", err)
	}
	return &ObjectMetadata{ContentLength: contentLength, ContentType: header.Get("Content-Type"), ETag: header.Get("ETag"), Metadata: extractUserMetadata(header)}, nil
}

// extractUserMetadata 提取 OSS 自定义元数据，并统一使用小写键供业务层稳定读取。
func extractUserMetadata(header http.Header) map[string]string {
	metadata := make(map[string]string)
	for key, values := range header {
		lowerKey := strings.ToLower(key)
		if len(values) > 0 && strings.HasPrefix(lowerKey, "x-oss-meta-") {
			metadata[strings.TrimPrefix(lowerKey, "x-oss-meta-")] = values[0]
		}
	}
	return metadata
}

// PresignGet 生成短期私有下载地址，供受信任的 Agent 或客户端使用。
func (c *Client) PresignGet(ctx context.Context, key string, expiresIn time.Duration) (string, error) {
	if key == "" || expiresIn <= 0 {
		return "", fmt.Errorf("OSS 下载参数无效")
	}
	url, err := c.bucket.SignURL(key, alioss.HTTPGet, int64(expiresIn/time.Second))
	if err != nil {
		return "", fmt.Errorf("生成 OSS 下载地址失败: %w", err)
	}
	return url, nil
}

// DeleteObject 删除指定 OSS 对象。
func (c *Client) DeleteObject(ctx context.Context, key string) error {
	if err := c.bucket.DeleteObject(key); err != nil {
		return fmt.Errorf("删除 OSS 对象失败: %w", err)
	}
	return nil
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
