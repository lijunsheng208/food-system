package server

import (
	"context"
	"errors"

	authv1 "github.com/lijunsheng/familyos/proto/gen/auth/v1"
	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/service"
)

// 业务状态码
const (
	CodeSuccess = 0

	CodeInvalidPhone     = 1001
	CodePasswordTooShort = 1002
	CodePhoneExists      = 1003
	CodeUserNotFound     = 1004
	CodePasswordWrong    = 1005
	CodeUserDisabled     = 1006
	CodeInternalError    = 1999
)

// AuthServer gRPC AuthService 实现
type AuthServer struct {
	authv1.UnimplementedAuthServiceServer
	svc *service.AuthService
}

// NewAuthServer 创建 AuthServer
func NewAuthServer(svc *service.AuthService) *AuthServer {
	return &AuthServer{svc: svc}
}

// Register 实现注册接口
func (s *AuthServer) Register(ctx context.Context, req *authv1.RegisterRequest) (*authv1.RegisterResponse, error) {
	result, err := s.svc.Register(ctx, req.Phone, req.Password, req.Nickname)
	if err != nil {
		return &authv1.RegisterResponse{
			Code:    mapErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &authv1.RegisterResponse{
		Code:    CodeSuccess,
		Message: "注册成功",
		Token:   result.Token,
		UserId:  int64(result.UserID),
	}, nil
}

// Login 实现登录接口
func (s *AuthServer) Login(ctx context.Context, req *authv1.LoginRequest) (*authv1.LoginResponse, error) {
	result, err := s.svc.Login(ctx, req.Phone, req.Password)
	if err != nil {
		return &authv1.LoginResponse{
			Code:    mapErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &authv1.LoginResponse{
		Code:    CodeSuccess,
		Message: "登录成功",
		Token:   result.Token,
		User:    toUserInfo(result.User),
	}, nil
}

// mapErrorCode 将业务错误映射为状态码
func mapErrorCode(err error) int32 {
	switch {
	case errors.Is(err, service.ErrInvalidPhone):
		return CodeInvalidPhone
	case errors.Is(err, service.ErrPasswordTooShort):
		return CodePasswordTooShort
	case errors.Is(err, service.ErrPhoneAlreadyExists):
		return CodePhoneExists
	case errors.Is(err, service.ErrUserNotFound):
		return CodeUserNotFound
	case errors.Is(err, service.ErrPasswordWrong):
		return CodePasswordWrong
	case errors.Is(err, service.ErrUserDisabled):
		return CodeUserDisabled
	default:
		return CodeInternalError
	}
}

// toUserInfo 将 model.User 转为 proto UserInfo
func toUserInfo(u *model.User) *authv1.UserInfo {
	info := &authv1.UserInfo{
		Id:       int64(u.ID),
		Phone:    u.Phone,
		Nickname: u.Nickname,
		Gender:   int32(u.Gender),
		Status:   int32(u.Status),
	}
	if u.Avatar != nil {
		info.Avatar = *u.Avatar
	}
	if u.LastLoginAt != nil {
		info.LastLoginAt = u.LastLoginAt.Format("2006-01-02 15:04:05")
	}
	info.CreatedAt = u.CreatedAt.Format("2006-01-02 15:04:05")
	info.UpdatedAt = u.UpdatedAt.Format("2006-01-02 15:04:05")
	return info
}
