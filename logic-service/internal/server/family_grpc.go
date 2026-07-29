package server

import (
	"context"
	"errors"

	familyv1 "github.com/lijunsheng/familyos/proto/gen/family/v1"
	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/service"
)

// 家庭模块状态码
const (
	// 成功
	FamilyCodeSuccess = 0

	// 家庭业务错误（对齐文档 2001-2009）
	FamilyCodeNotFound     = 2001
	FamilyCodeAlreadyIn    = 2002
	FamilyCodeNotIn        = 2003
	FamilyCodeNoPermission = 2004
	FamilyCodeInvalidCode  = 2005
	FamilyCodeFull         = 2006
	FamilyCodeCannotOpOwner = 2007
	FamilyCodeInvalidName  = 2008
	FamilyCodeMemberNotFound = 2009
)

// FamilyServer gRPC FamilyService 实现
type FamilyServer struct {
	familyv1.UnimplementedFamilyServiceServer
	svc *service.FamilyService
}

// NewFamilyServer 创建 FamilyServer
func NewFamilyServer(svc *service.FamilyService) *FamilyServer {
	return &FamilyServer{svc: svc}
}

// ─── GetMyFamily ─────────────────────────────────────────────

func (s *FamilyServer) GetMyFamily(ctx context.Context, req *familyv1.GetMyFamilyRequest) (*familyv1.GetMyFamilyResponse, error) {
	result, err := s.svc.GetMyFamily(ctx, uint64(req.UserId))
	if err != nil {
		return &familyv1.GetMyFamilyResponse{
			Code:    CodeInternalError,
			Message: err.Error(),
		}, nil
	}

	if result.Family == nil {
		return &familyv1.GetMyFamilyResponse{
			Code:    FamilyCodeSuccess,
			Message: "暂未加入家庭",
			Family:  nil,
		}, nil
	}

	return &familyv1.GetMyFamilyResponse{
		Code:    FamilyCodeSuccess,
		Message: "查询成功",
		Family:  toFamilyInfo(result.Family, result.MyRole),
	}, nil
}

// ─── CreateFamily ────────────────────────────────────────────

func (s *FamilyServer) CreateFamily(ctx context.Context, req *familyv1.CreateFamilyRequest) (*familyv1.CreateFamilyResponse, error) {
	var avatar, description *string
	if req.Avatar != "" {
		avatar = &req.Avatar
	}
	if req.Description != "" {
		description = &req.Description
	}

	result, err := s.svc.CreateFamily(ctx, uint64(req.UserId), req.Name, avatar, description)
	if err != nil {
		return &familyv1.CreateFamilyResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CreateFamilyResponse{
		Code:       FamilyCodeSuccess,
		Message:    "创建成功",
		FamilyId:   int64(result.FamilyID),
		InviteCode: result.InviteCode,
	}, nil
}

// ─── UpdateFamily ────────────────────────────────────────────

func (s *FamilyServer) UpdateFamily(ctx context.Context, req *familyv1.UpdateFamilyRequest) (*familyv1.CommonResponse, error) {
	// name: 为空不修改（不允许清空家庭名称）
	var name *string
	if req.Name != "" {
		name = &req.Name
	}
	// avatar / description: 始终传指针（空字符串表示清空）
	avatar := &req.Avatar
	description := &req.Description

	err := s.svc.UpdateFamily(ctx, uint64(req.UserId), uint64(req.FamilyId), name, avatar, description)
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "更新成功",
	}, nil
}

// ─── JoinFamily ──────────────────────────────────────────────

func (s *FamilyServer) JoinFamily(ctx context.Context, req *familyv1.JoinFamilyRequest) (*familyv1.JoinFamilyResponse, error) {
	var relation, displayName *string
	if req.Relation != "" {
		relation = &req.Relation
	}
	if req.DisplayName != "" {
		displayName = &req.DisplayName
	}

	result, err := s.svc.JoinFamily(ctx, uint64(req.UserId), req.InviteCode, relation, displayName)
	if err != nil {
		return &familyv1.JoinFamilyResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.JoinFamilyResponse{
		Code:     FamilyCodeSuccess,
		Message:  "加入成功",
		FamilyId: int64(result.FamilyID),
	}, nil
}

// ─── LeaveFamily ─────────────────────────────────────────────

func (s *FamilyServer) LeaveFamily(ctx context.Context, req *familyv1.LeaveFamilyRequest) (*familyv1.CommonResponse, error) {
	err := s.svc.LeaveFamily(ctx, uint64(req.UserId))
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "退出成功",
	}, nil
}

// ─── DissolveFamily ──────────────────────────────────────────

func (s *FamilyServer) DissolveFamily(ctx context.Context, req *familyv1.DissolveFamilyRequest) (*familyv1.CommonResponse, error) {
	err := s.svc.DissolveFamily(ctx, uint64(req.UserId), uint64(req.FamilyId))
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "解散成功",
	}, nil
}

// ─── ListMembers ─────────────────────────────────────────────

func (s *FamilyServer) ListMembers(ctx context.Context, req *familyv1.ListMembersRequest) (*familyv1.ListMembersResponse, error) {
	members, err := s.svc.ListMembers(ctx, uint64(req.UserId), uint64(req.FamilyId))
	if err != nil {
		return &familyv1.ListMembersResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	infos := make([]*familyv1.FamilyMemberInfo, 0, len(members))
	for _, m := range members {
		infos = append(infos, toFamilyMemberInfo(&m))
	}

	return &familyv1.ListMembersResponse{
		Code:    FamilyCodeSuccess,
		Message: "查询成功",
		Members: infos,
	}, nil
}

// ─── UpdateMember ────────────────────────────────────────────

func (s *FamilyServer) UpdateMember(ctx context.Context, req *familyv1.UpdateMemberRequest) (*familyv1.CommonResponse, error) {
	// role: 0 = 不修改，>0 = 修改为新角色
	var role *int32
	if req.Role > 0 {
		role = &req.Role
	}
	// relation / display_name: 始终传指针（空字符串表示清空字段）
	relation := &req.Relation
	displayName := &req.DisplayName

	err := s.svc.UpdateMember(ctx,
		uint64(req.OperatorUserId),
		uint64(req.FamilyId),
		uint64(req.MemberUserId),
		role, relation, displayName,
	)
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "更新成功",
	}, nil
}

// ─── RemoveMember ────────────────────────────────────────────

func (s *FamilyServer) RemoveMember(ctx context.Context, req *familyv1.RemoveMemberRequest) (*familyv1.CommonResponse, error) {
	err := s.svc.RemoveMember(ctx,
		uint64(req.OperatorUserId),
		uint64(req.FamilyId),
		uint64(req.MemberUserId),
	)
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "移除成功",
	}, nil
}

// ─── ResetInviteCode ─────────────────────────────────────────

func (s *FamilyServer) ResetInviteCode(ctx context.Context, req *familyv1.ResetInviteCodeRequest) (*familyv1.ResetInviteCodeResponse, error) {
	var expireHours *int32
	if req.ExpireHours > 0 {
		expireHours = &req.ExpireHours
	}

	result, err := s.svc.ResetInviteCode(ctx, uint64(req.UserId), uint64(req.FamilyId), expireHours)
	if err != nil {
		return &familyv1.ResetInviteCodeResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	expiredAtStr := ""
	if result.InviteCodeExpiredAt != nil {
		expiredAtStr = result.InviteCodeExpiredAt.Format("2006-01-02 15:04:05")
	}

	return &familyv1.ResetInviteCodeResponse{
		Code:                 FamilyCodeSuccess,
		Message:              "重置成功",
		InviteCode:           result.InviteCode,
		InviteCodeExpiredAt:  expiredAtStr,
	}, nil
}

// ─── 错误码映射 ──────────────────────────────────────────────

func mapFamilyErrorCode(err error) int32 {
	switch {
	case errors.Is(err, service.ErrFamilyNotFound):
		return FamilyCodeNotFound
	case errors.Is(err, service.ErrUserAlreadyInFamily):
		return FamilyCodeAlreadyIn
	case errors.Is(err, service.ErrUserNotInFamily):
		return FamilyCodeNotIn
	case errors.Is(err, service.ErrNoFamilyPermission):
		return FamilyCodeNoPermission
	case errors.Is(err, service.ErrInvalidInviteCode):
		return FamilyCodeInvalidCode
	case errors.Is(err, service.ErrFamilyFull):
		return FamilyCodeFull
	case errors.Is(err, service.ErrCannotOperateOwner):
		return FamilyCodeCannotOpOwner
	case errors.Is(err, service.ErrInvalidFamilyName):
		return FamilyCodeInvalidName
	case errors.Is(err, service.ErrMemberNotFound):
		return FamilyCodeMemberNotFound
	case errors.Is(err, service.ErrUserNotFound):
		return CodeUserNotFound
	default:
		return CodeInternalError
	}
}

// ─── Proto 转换 ──────────────────────────────────────────────

func toFamilyInfo(f *model.Family, myRole int8) *familyv1.FamilyInfo {
	info := &familyv1.FamilyInfo{
		Id:             int64(f.ID),
		Name:           f.Name,
		OwnerUserId:    int64(f.OwnerUserID),
		InviteCode:     f.InviteCode,
		MemberCount:    int32(f.MemberCount),
		MaxMemberCount: int32(f.MaxMemberCount),
		MyRole:         int32(myRole),
		CreatedAt:      f.CreatedAt.Format("2006-01-02 15:04:05"),
		UpdatedAt:      f.UpdatedAt.Format("2006-01-02 15:04:05"),
	}
	if f.Avatar != nil {
		info.Avatar = *f.Avatar
	}
	if f.Description != nil {
		info.Description = *f.Description
	}
	return info
}

func toFamilyMemberInfo(m *model.FamilyMemberWithUser) *familyv1.FamilyMemberInfo {
	info := &familyv1.FamilyMemberInfo{
		UserId:  int64(m.UserID),
		Phone:   m.Phone,
		Nickname: m.Nickname,
		Role:    int32(m.Role),
		JoinedAt: m.JoinedAt.Format("2006-01-02 15:04:05"),
	}
	if m.Avatar != nil {
		info.Avatar = *m.Avatar
	}
	if m.Relation != nil {
		info.Relation = *m.Relation
	}
	if m.DisplayName != nil {
		info.DisplayName = *m.DisplayName
	}
	return info
}
