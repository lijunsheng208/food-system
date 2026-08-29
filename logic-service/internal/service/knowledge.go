package service

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"log"
	"path/filepath"
	"strings"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
	"github.com/lijunsheng/familyos/pkg/oss"
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
	if sha != "" && (len(sha) != 64 || strings.ToLower(sha) != sha) {
		return 0, "", nil, ErrKnowledgeInvalid
	}
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		return 0, "", nil, err
	}
	sessionID := fmt.Sprintf("%x", raw)
	key := fmt.Sprintf("%s/%d/%s%s", strings.Trim(s.prefix, "/"), baseID, sessionID, ext)
	doc := &model.KnowledgeDocument{KnowledgeBaseID: baseID, CreatedBy: userID, Title: strings.TrimSuffix(filepath.Base(filename), ext), OriginalFilename: filename, FileExtension: ext, MimeType: contentType, OSSBucket: s.bucket, OSSObjectKey: key, Status: model.DocumentUploading, IndexVersion: 1}
	var declaredSHA *string
	if sha != "" {
		declaredSHA = &sha
	}
	session := &model.KnowledgeUploadSession{ID: sessionID, KnowledgeBaseID: baseID, CreatedBy: userID, OSSBucket: s.bucket, OSSObjectKey: key, OriginalFilename: filename, DeclaredMimeType: contentType, DeclaredFileSize: uint64(size), DeclaredSHA256: declaredSHA, Status: 0, ExpiresAt: time.Now().Add(s.ttl)}
	expiresAt := session.ExpiresAt
	doc.UploadExpiresAt = &expiresAt
	if err := s.repo.CreateUpload(ctx, doc, session); err != nil {
		return 0, "", nil, err
	}
	metadata := map[string]string{"document-id": fmt.Sprint(doc.ID), "upload-session-id": sessionID}
	if sha != "" {
		metadata["sha256"] = sha
	}
	signed, err := s.storage.PresignPut(ctx, oss.PresignPutInput{Key: key, ContentType: contentType, Metadata: metadata, ExpiresIn: s.ttl})
	return doc.ID, sessionID, signed, err
}

// CompleteUpload 校验 OSS 对象并推进文档状态。
func (s *KnowledgeService) CompleteUpload(ctx context.Context, userID, documentID uint64) (*model.KnowledgeDocument, error) {
	doc, session, err := s.repo.GetDocumentWithSession(ctx, documentID)
	if err != nil || doc == nil || session == nil {
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
	if session.Status != model.UploadSessionPending || !session.ExpiresAt.After(time.Now()) {
		return nil, ErrKnowledgeExpired
	}
	meta, err := s.storage.HeadObject(ctx, doc.OSSObjectKey)
	if err != nil {
		log.Printf("查询 OSS 上传对象失败: document_id=%d object_key=%q err=%v", doc.ID, doc.OSSObjectKey, err)
		return nil, ErrKnowledgeObjectMissing
	}
	if mismatch := validateUploadMetadata(meta, doc, session); mismatch != "" {
		log.Printf("OSS 上传对象元数据校验失败: document_id=%d object_key=%q %s", doc.ID, doc.OSSObjectKey, mismatch)
		return nil, ErrKnowledgeMetadataMismatch
	}
	return s.repo.CompleteUpload(ctx, documentID, uint64(meta.ContentLength), meta.ETag, session.DeclaredSHA256)
}

// validateUploadMetadata 对比上传声明与 OSS 对象属性，返回仅用于内部日志的具体失败上下文。
func validateUploadMetadata(meta *oss.ObjectMetadata, doc *model.KnowledgeDocument, session *model.KnowledgeUploadSession) string {
	if meta.ContentLength != int64(session.DeclaredFileSize) || meta.ContentLength <= 0 || meta.ContentLength > 20*1024*1024 {
		return fmt.Sprintf("field=content_length expected=%d actual=%d allowed_max=%d", session.DeclaredFileSize, meta.ContentLength, 20*1024*1024)
	}
	if meta.ContentType != session.DeclaredMimeType {
		return fmt.Sprintf("field=content_type expected=%q actual=%q", session.DeclaredMimeType, meta.ContentType)
	}
	expectedDocumentID := fmt.Sprint(doc.ID)
	if meta.Metadata["document-id"] != expectedDocumentID {
		return fmt.Sprintf("field=document-id expected=%q actual=%q", expectedDocumentID, meta.Metadata["document-id"])
	}
	if meta.Metadata["upload-session-id"] != session.ID {
		return fmt.Sprintf("field=upload-session-id expected=%q actual=%q", session.ID, meta.Metadata["upload-session-id"])
	}
	if session.DeclaredSHA256 != nil && meta.Metadata["sha256"] != *session.DeclaredSHA256 {
		return fmt.Sprintf("field=sha256 expected=%q actual=%q", *session.DeclaredSHA256, meta.Metadata["sha256"])
	}
	return ""
}

// DeleteDocument 校验访问权限后请求删除文档的全部索引版本。
func (s *KnowledgeService) DeleteDocument(ctx context.Context, userID, documentID uint64) (*model.KnowledgeDocument, error) {
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
		if member.Role == model.FamilyRoleMember && doc.CreatedBy != userID {
			return nil, ErrKnowledgePermission
		}
	}
	return s.repo.RequestDocumentDeletion(ctx, documentID)
}
