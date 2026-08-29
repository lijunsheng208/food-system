package service

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
	"github.com/lijunsheng/familyos/pkg/oss"
	"path/filepath"
	"strings"
	"time"
)

var ErrKnowledgeInvalid = errors.New("知识库上传参数无效")
var ErrKnowledgePermission = errors.New("无知识库访问权限")
var ErrKnowledgeNotFound = errors.New("知识库或文档不存在")
var ErrKnowledgeExpired = errors.New("上传会话已过期")
var ErrKnowledgeObjectMissing = errors.New("文件尚未上传成功或已被清理")
var ErrKnowledgeMetadataMismatch = errors.New("OSS 文件元数据校验失败")

// KnowledgeService 负责知识库文档上传票据和确认流程。
type KnowledgeService struct {
	repo       *repository.KnowledgeRepo
	familyRepo *repository.FamilyRepo
	storage    *oss.Client
	bucket     string
	prefix     string
	ttl        time.Duration
}

// EnsurePersonalKnowledgeBase 获取或创建当前用户的默认个人知识库。
func (s *KnowledgeService) EnsurePersonalKnowledgeBase(ctx context.Context, userID uint64) (*model.KnowledgeBase, error) {
	if userID == 0 {
		return nil, ErrKnowledgePermission
	}
	return s.repo.GetOrCreatePersonalBase(ctx, userID)
}

// NewKnowledgeService 创建知识库服务。
func NewKnowledgeService(repo *repository.KnowledgeRepo, familyRepo *repository.FamilyRepo, storage *oss.Client, bucket, prefix string, ttl time.Duration) *KnowledgeService {
	return &KnowledgeService{repo: repo, familyRepo: familyRepo, storage: storage, bucket: bucket, prefix: prefix, ttl: ttl}
}

// CreateUploadTicket 创建个人或家庭知识库的 OSS 直传票据。
func (s *KnowledgeService) CreateUploadTicket(ctx context.Context, userID, baseID uint64, filename, contentType string, size int64, sha string) (uint64, string, *oss.PresignedPut, error) {
	base, err := s.repo.GetBase(ctx, baseID)
	if err != nil || base == nil {
		return 0, "", nil, ErrKnowledgeNotFound
	}
	if base.ScopeType == model.KnowledgeScopePersonal && (base.OwnerUserID == nil || *base.OwnerUserID != userID) {
		return 0, "", nil, ErrKnowledgePermission
	}
	if base.ScopeType == model.KnowledgeScopeFamily {
		if s.familyRepo == nil || base.FamilyID == nil {
			return 0, "", nil, ErrKnowledgePermission
		}
		member, memberErr := s.familyRepo.GetMember(ctx, *base.FamilyID, userID)
		if memberErr != nil || member == nil {
			return 0, "", nil, ErrKnowledgePermission
		}
	}
	ext := strings.ToLower(filepath.Ext(filename))
	allowed := map[string]bool{".pdf": true, ".docx": true, ".txt": true, ".md": true}
	if !allowed[ext] || size <= 0 || size > 20*1024*1024 || contentType == "" {
		return 0, "", nil, ErrKnowledgeInvalid
	}
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		return 0, "", nil, err
	}
	sessionID := fmt.Sprintf("%x", raw)
	key := fmt.Sprintf("%s/%d/%s%s", strings.Trim(s.prefix, "/"), baseID, sessionID, ext)
	doc := &model.KnowledgeDocument{KnowledgeBaseID: baseID, CreatedBy: userID, Title: strings.TrimSuffix(filepath.Base(filename), ext), OriginalFilename: filename, FileExtension: ext, MimeType: contentType, OSSBucket: s.bucket, OSSObjectKey: key, Status: model.DocumentUploading, IndexVersion: 1}
	session := &model.KnowledgeUploadSession{ID: sessionID, KnowledgeBaseID: baseID, CreatedBy: userID, OSSBucket: s.bucket, OSSObjectKey: key, OriginalFilename: filename, DeclaredMimeType: contentType, DeclaredFileSize: uint64(size), Status: 0, ExpiresAt: time.Now().Add(s.ttl)}
	expiresAt := session.ExpiresAt
	doc.UploadExpiresAt = &expiresAt
	if err := s.repo.CreateUpload(ctx, doc, session); err != nil {
		return 0, "", nil, err
	}
	signed, err := s.storage.PresignPut(ctx, oss.PresignPutInput{Key: key, ContentType: contentType, Metadata: map[string]string{"document-id": fmt.Sprint(doc.ID), "upload-session-id": sessionID}, ExpiresIn: s.ttl})
	return doc.ID, sessionID, signed, err
}

// CompleteUpload 校验 OSS 对象并推进文档状态。
func (s *KnowledgeService) CompleteUpload(ctx context.Context, userID, documentID uint64) (*model.KnowledgeDocument, error) {
	doc, err := s.repo.GetDocument(ctx, documentID)
	if err != nil || doc == nil {
		return nil, ErrKnowledgeNotFound
	}
	base, err := s.repo.GetBase(ctx, doc.KnowledgeBaseID)
	if err != nil || base == nil {
		return nil, ErrKnowledgeNotFound
	}
	if base.ScopeType == model.KnowledgeScopePersonal && (base.OwnerUserID == nil || *base.OwnerUserID != userID) {
		return nil, ErrKnowledgePermission
	}
	if base.ScopeType == model.KnowledgeScopeFamily {
		if s.familyRepo == nil || base.FamilyID == nil {
			return nil, ErrKnowledgePermission
		}
		member, memberErr := s.familyRepo.GetMember(ctx, *base.FamilyID, userID)
		if memberErr != nil || member == nil {
			return nil, ErrKnowledgePermission
		}
	}
	if doc.Status != model.DocumentUploading {
		return doc, nil
	}
	meta, err := s.storage.HeadObject(ctx, doc.OSSObjectKey)
	if err != nil {
		return nil, ErrKnowledgeObjectMissing
	}
	if meta.ContentLength <= 0 || meta.ContentLength > 20*1024*1024 {
		return nil, ErrKnowledgeMetadataMismatch
	}
	if meta.ContentType != "" && meta.ContentType != doc.MimeType {
		return nil, ErrKnowledgeMetadataMismatch
	}
	return s.repo.CompleteUpload(ctx, documentID, uint64(meta.ContentLength), meta.ETag)
}
