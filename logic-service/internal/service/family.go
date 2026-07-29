package service

import (
	"context"
	"crypto/rand"
	"errors"
	"math/big"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
)

// 家庭模块业务错误
var (
	ErrFamilyNotFound     = errors.New("家庭不存在")
	ErrUserAlreadyInFamily = errors.New("用户已加入家庭")
	ErrUserNotInFamily    = errors.New("用户未加入家庭")
	ErrNoFamilyPermission = errors.New("无家庭操作权限")
	ErrInvalidInviteCode  = errors.New("邀请码无效或已过期")
	ErrFamilyFull         = errors.New("家庭成员数量已达上限")
	ErrCannotOperateOwner = errors.New("不能操作家庭所有者")
	ErrInvalidFamilyName  = errors.New("家庭名称不合法")
	ErrMemberNotFound     = errors.New("成员不存在")
)

// FamilyService 家庭业务逻辑
type FamilyService struct {
	familyRepo *repository.FamilyRepo
	userRepo   *repository.UserRepo
}

// NewFamilyService 创建 FamilyService
func NewFamilyService(familyRepo *repository.FamilyRepo, userRepo *repository.UserRepo) *FamilyService {
	return &FamilyService{
		familyRepo: familyRepo,
		userRepo:   userRepo,
	}
}

// ─── 查询我的家庭 ─────────────────────────────────────────────

// GetMyFamilyResult 查询结果
type GetMyFamilyResult struct {
	Family *model.Family
	MyRole int8
}

// GetMyFamily 查询用户当前所属家庭
func (s *FamilyService) GetMyFamily(ctx context.Context, userID uint64) (*GetMyFamilyResult, error) {
	member, err := s.familyRepo.GetMemberByUserID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if member == nil {
		// 未加入家庭，返回 nil family
		return &GetMyFamilyResult{Family: nil, MyRole: 0}, nil
	}

	family, err := s.familyRepo.GetFamilyByID(ctx, member.FamilyID)
	if err != nil {
		return nil, err
	}
	if family == nil || family.Status == model.FamilyStatusDissolve {
		return &GetMyFamilyResult{Family: nil, MyRole: 0}, nil
	}

	return &GetMyFamilyResult{Family: family, MyRole: member.Role}, nil
}

// ─── 创建家庭 ─────────────────────────────────────────────────

// CreateFamilyResult 创建结果
type CreateFamilyResult struct {
	FamilyID   uint64
	InviteCode string
}

// CreateFamily 创建家庭并自动成为所有者
func (s *FamilyService) CreateFamily(ctx context.Context, userID uint64, name string, avatar, description *string) (*CreateFamilyResult, error) {
	// 1. 校验家庭名称
	if name == "" || len(name) > 50 {
		return nil, ErrInvalidFamilyName
	}

	// 2. 校验用户是否存在
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if user == nil {
		return nil, ErrUserNotFound
	}

	// 3. 校验用户是否已加入家庭
	existingMember, err := s.familyRepo.GetMemberByUserID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if existingMember != nil {
		return nil, ErrUserAlreadyInFamily
	}

	// 4. 生成唯一邀请码
	inviteCode, err := s.generateUniqueInviteCode(ctx)
	if err != nil {
		return nil, err
	}

	// 5. 事务创建
	family := &model.Family{
		Name:        name,
		Avatar:      avatar,
		Description: description,
		OwnerUserID: userID,
		InviteCode:  inviteCode,
		MemberCount: 1,
		MaxMemberCount: 20,
		Status:      model.FamilyStatusNormal,
	}
	member := &model.FamilyMember{
		UserID: userID,
		Role:   model.FamilyRoleOwner,
		JoinedAt: time.Now(),
	}

	if err := s.familyRepo.CreateFamilyWithOwner(ctx, family, member); err != nil {
		return nil, err
	}

	return &CreateFamilyResult{
		FamilyID:   family.ID,
		InviteCode: inviteCode,
	}, nil
}

// ─── 修改家庭信息 ─────────────────────────────────────────────

// UpdateFamily 修改家庭信息
func (s *FamilyService) UpdateFamily(ctx context.Context, userID, familyID uint64, name, avatar, description *string) error {
	// 1. 校验家庭成员身份和权限
	member, err := s.familyRepo.GetMember(ctx, familyID, userID)
	if err != nil {
		return err
	}
	if member == nil {
		return ErrUserNotInFamily
	}
	if !canManageFamily(member.Role) {
		return ErrNoFamilyPermission
	}

	// 2. 校验家庭存在且状态正常
	family, err := s.familyRepo.GetFamilyByID(ctx, familyID)
	if err != nil {
		return err
	}
	if family == nil || family.Status == model.FamilyStatusDissolve {
		return ErrFamilyNotFound
	}

	// 3. 增量更新
	updates := make(map[string]interface{})
	if name != nil && *name != "" {
		if len(*name) > 50 {
			return ErrInvalidFamilyName
		}
		updates["name"] = *name
	}
	// avatar / description 任何时候都更新（空字符串 → 清空为 NULL）
	if avatar != nil {
		if *avatar == "" {
			updates["avatar"] = nil
		} else {
			updates["avatar"] = *avatar
		}
	}
	if description != nil {
		if *description == "" {
			updates["description"] = nil
		} else {
			updates["description"] = *description
		}
	}
	if len(updates) == 0 {
		return nil
	}

	return s.familyRepo.UpdateFamily(ctx, familyID, updates)
}

// ─── 通过邀请码加入家庭 ────────────────────────────────────────

// JoinFamilyResult 加入结果
type JoinFamilyResult struct {
	FamilyID uint64
}

// JoinFamily 通过邀请码加入家庭
func (s *FamilyService) JoinFamily(ctx context.Context, userID uint64, inviteCode string, relation, displayName *string) (*JoinFamilyResult, error) {
	// 1. 校验用户是否存在
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if user == nil {
		return nil, ErrUserNotFound
	}

	// 2. 校验用户是否已加入家庭
	existingMember, err := s.familyRepo.GetMemberByUserID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if existingMember != nil {
		return nil, ErrUserAlreadyInFamily
	}

	// 3. 校验邀请码
	family, err := s.familyRepo.GetFamilyByInviteCode(ctx, inviteCode)
	if err != nil {
		return nil, err
	}
	if family == nil {
		return nil, ErrInvalidInviteCode
	}

	// 4. 校验邀请码是否过期
	if family.InviteCodeExpiredAt != nil && time.Now().After(*family.InviteCodeExpiredAt) {
		return nil, ErrInvalidInviteCode
	}

	// 5. 校验成员数量
	if family.MemberCount >= family.MaxMemberCount {
		return nil, ErrFamilyFull
	}

	// 6. 插入成员
	member := &model.FamilyMember{
		FamilyID:    family.ID,
		UserID:      userID,
		Role:        model.FamilyRoleMember,
		Relation:    relation,
		DisplayName: displayName,
		JoinedAt:    time.Now(),
	}
	if err := s.familyRepo.JoinFamily(ctx, family.ID, member); err != nil {
		return nil, err
	}

	return &JoinFamilyResult{FamilyID: family.ID}, nil
}

// ─── 退出家庭 ─────────────────────────────────────────────────

// LeaveFamily 退出家庭
func (s *FamilyService) LeaveFamily(ctx context.Context, userID uint64) error {
	// 1. 校验用户是否在家庭中
	member, err := s.familyRepo.GetMemberByUserID(ctx, userID)
	if err != nil {
		return err
	}
	if member == nil {
		return ErrUserNotInFamily
	}

	// 2. 所有者不能退出
	if member.Role == model.FamilyRoleOwner {
		return ErrCannotOperateOwner
	}

	// 3. 退出家庭
	return s.familyRepo.LeaveFamily(ctx, member.FamilyID, userID)
}

// ─── 解散家庭 ─────────────────────────────────────────────────

// DissolveFamily 解散家庭（仅所有者）
func (s *FamilyService) DissolveFamily(ctx context.Context, userID, familyID uint64) error {
	// 1. 校验家庭成员身份
	member, err := s.familyRepo.GetMember(ctx, familyID, userID)
	if err != nil {
		return err
	}
	if member == nil {
		return ErrUserNotInFamily
	}
	if member.Role != model.FamilyRoleOwner {
		return ErrNoFamilyPermission
	}

	// 2. 校验家庭状态
	family, err := s.familyRepo.GetFamilyByID(ctx, familyID)
	if err != nil {
		return err
	}
	if family == nil || family.Status == model.FamilyStatusDissolve {
		return ErrFamilyNotFound
	}

	// 3. 解散
	return s.familyRepo.DissolveFamily(ctx, familyID)
}

// ─── 查询成员列表 ─────────────────────────────────────────────

// ListMembers 查询家庭成员列表
func (s *FamilyService) ListMembers(ctx context.Context, userID, familyID uint64) ([]model.FamilyMemberWithUser, error) {
	// 1. 校验家庭成员身份
	member, err := s.familyRepo.GetMember(ctx, familyID, userID)
	if err != nil {
		return nil, err
	}
	if member == nil {
		return nil, ErrNoFamilyPermission
	}

	// 2. 校验家庭状态
	family, err := s.familyRepo.GetFamilyByID(ctx, familyID)
	if err != nil {
		return nil, err
	}
	if family == nil || family.Status == model.FamilyStatusDissolve {
		return nil, ErrFamilyNotFound
	}

	// 3. 查询成员列表
	return s.familyRepo.ListMembers(ctx, familyID)
}

// ─── 修改成员信息 ─────────────────────────────────────────────

// UpdateMember 修改成员信息
func (s *FamilyService) UpdateMember(ctx context.Context, operatorUserID, familyID, memberUserID uint64, role *int32, relation, displayName *string) error {
	// 1. 校验操作者身份
	operator, err := s.familyRepo.GetMember(ctx, familyID, operatorUserID)
	if err != nil {
		return err
	}
	if operator == nil {
		return ErrNoFamilyPermission
	}
	if !canManageFamily(operator.Role) {
		return ErrNoFamilyPermission
	}

	// 2. 校验目标成员
	target, err := s.familyRepo.GetMember(ctx, familyID, memberUserID)
	if err != nil {
		return err
	}
	if target == nil {
		return ErrMemberNotFound
	}
	if target.Role == model.FamilyRoleOwner {
		return ErrCannotOperateOwner
	}

	// 3. 权限细分
	updates := make(map[string]interface{})

	// 角色变更 — 仅所有者可改
	if role != nil {
		if operator.Role != model.FamilyRoleOwner {
			return ErrNoFamilyPermission
		}
		updates["role"] = int8(*role)
	}

	// 备注变更 — 所有者可改所有人，管理员只可改普通成员
	// 始终更新 relation / display_name（空字符串表示清空为 NULL）
	if relation != nil {
		if operator.Role == model.FamilyRoleAdmin && target.Role != model.FamilyRoleMember {
			return ErrNoFamilyPermission
		}
		if *relation == "" {
			updates["relation"] = nil // 清空 → NULL
		} else {
			updates["relation"] = *relation
		}
	}
	if displayName != nil {
		if operator.Role == model.FamilyRoleAdmin && target.Role != model.FamilyRoleMember {
			return ErrNoFamilyPermission
		}
		if *displayName == "" {
			updates["display_name"] = nil // 清空 → NULL
		} else {
			updates["display_name"] = *displayName
		}
	}

	if len(updates) == 0 {
		return nil
	}

	return s.familyRepo.UpdateMember(ctx, familyID, memberUserID, updates)
}

// ─── 移除成员 ─────────────────────────────────────────────────

// RemoveMember 移除成员
func (s *FamilyService) RemoveMember(ctx context.Context, operatorUserID, familyID, memberUserID uint64) error {
	// 1. 校验操作者身份
	operator, err := s.familyRepo.GetMember(ctx, familyID, operatorUserID)
	if err != nil {
		return err
	}
	if operator == nil {
		return ErrNoFamilyPermission
	}

	// 2. 校验目标成员
	target, err := s.familyRepo.GetMember(ctx, familyID, memberUserID)
	if err != nil {
		return err
	}
	if target == nil {
		return ErrMemberNotFound
	}
	if target.Role == model.FamilyRoleOwner {
		return ErrCannotOperateOwner
	}

	// 3. 权限判断
	if !canRemoveMember(operator.Role, target.Role) {
		return ErrNoFamilyPermission
	}

	// 4. 移除
	return s.familyRepo.RemoveMember(ctx, familyID, memberUserID)
}

// ─── 重置邀请码 ───────────────────────────────────────────────

// ResetInviteCodeResult 重置结果
type ResetInviteCodeResult struct {
	InviteCode          string
	InviteCodeExpiredAt *time.Time
}

// ResetInviteCode 重置邀请码
func (s *FamilyService) ResetInviteCode(ctx context.Context, userID, familyID uint64, expireHours *int32) (*ResetInviteCodeResult, error) {
	// 1. 校验权限
	member, err := s.familyRepo.GetMember(ctx, familyID, userID)
	if err != nil {
		return nil, err
	}
	if member == nil || !canManageFamily(member.Role) {
		return nil, ErrNoFamilyPermission
	}

	// 2. 校验家庭状态
	family, err := s.familyRepo.GetFamilyByID(ctx, familyID)
	if err != nil {
		return nil, err
	}
	if family == nil || family.Status == model.FamilyStatusDissolve {
		return nil, ErrFamilyNotFound
	}

	// 3. 生成新邀请码
	newCode, err := s.generateUniqueInviteCode(ctx)
	if err != nil {
		return nil, err
	}

	// 4. 计算过期时间
	var expiredAt *time.Time
	if expireHours != nil && *expireHours > 0 {
		t := time.Now().Add(time.Duration(*expireHours) * time.Hour)
		expiredAt = &t
	}

	// 5. 更新
	if err := s.familyRepo.ResetInviteCode(ctx, familyID, newCode, expiredAt); err != nil {
		return nil, err
	}

	return &ResetInviteCodeResult{
		InviteCode:          newCode,
		InviteCodeExpiredAt: expiredAt,
	}, nil
}

// ─── 权限工具函数 ─────────────────────────────────────────────

func canManageFamily(role int8) bool {
	return role == model.FamilyRoleOwner || role == model.FamilyRoleAdmin
}

func canRemoveMember(operatorRole, targetRole int8) bool {
	if targetRole == model.FamilyRoleOwner {
		return false
	}
	if operatorRole == model.FamilyRoleOwner {
		return true
	}
	return operatorRole == model.FamilyRoleAdmin && targetRole == model.FamilyRoleMember
}

// ─── 邀请码生成 ───────────────────────────────────────────────

const inviteCodeChars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
const inviteCodeLength = 6

// generateUniqueInviteCode 生成唯一邀请码，重试直到不冲突
func (s *FamilyService) generateUniqueInviteCode(ctx context.Context) (string, error) {
	for i := 0; i < 10; i++ {
		code, err := randomString(inviteCodeLength)
		if err != nil {
			return "", err
		}
		// 查重
		existing, err := s.familyRepo.GetFamilyByInviteCode(ctx, code)
		if err != nil {
			return "", err
		}
		if existing == nil {
			return code, nil
		}
	}
	return "", errors.New("无法生成唯一邀请码，请重试")
}

func randomString(n int) (string, error) {
	b := make([]byte, n)
	for i := range b {
		idx, err := rand.Int(rand.Reader, big.NewInt(int64(len(inviteCodeChars))))
		if err != nil {
			return "", err
		}
		b[i] = inviteCodeChars[idx.Int64()]
	}
	return string(b), nil
}
