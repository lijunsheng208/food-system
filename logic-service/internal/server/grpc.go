package server

import (
	"context"
	"errors"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/service"
	authv1 "github.com/lijunsheng/familyos/proto/gen/auth/v1"
)

// 业务状态码
const (
	CodeSuccess = 0

	CodeInvalidPhone        = 1001
	CodePasswordTooShort    = 1002
	CodePhoneExists         = 1003
	CodeUserNotFound        = 1004
	CodePasswordWrong       = 1005
	CodeUserDisabled        = 1006
	CodeSMSCooldown         = 1007
	CodeSMSDailyLimit       = 1008
	CodeSMSIPLimit          = 1009
	CodeSMSSendFailed       = 1010
	CodeSMSUnavailable      = 1011
	CodeSMSCodeInvalid      = 1012
	CodeSMSAttemptsLimit    = 1013
	CodePasswordNotSet      = 1014
	CodeRefreshInvalid      = 1015
	CodeRefreshReused       = 1016
	CodeSessionUnavailable  = 1017
	CodeDietaryUnavailable  = 1020
	CodeDietaryTypeInvalid  = 1021
	CodeDietaryValueInvalid = 1022
	CodeDietaryDuplicate    = 1023
	CodeInternalError       = 1999
)

// AuthServer gRPC AuthService 实现
type AuthServer struct {
	authv1.UnimplementedAuthServiceServer
	svc *service.AuthService
}

// SMSLogin 实现短信验证码登录和自动注册。
func (s *AuthServer) SMSLogin(ctx context.Context, req *authv1.SMSLoginRequest) (*authv1.SMSLoginResponse, error) {
	result, err := s.svc.SMSLogin(ctx, req.GetPhone(), req.GetVerificationCode(), req.GetDeviceId())
	if err != nil {
		return &authv1.SMSLoginResponse{
			Code:    mapErrorCode(err),
			Message: publicAuthErrorMessage(err),
		}, nil
	}
	return &authv1.SMSLoginResponse{
		Code:         CodeSuccess,
		Message:      "登录成功",
		IsNewUser:    result.IsNewUser,
		User:         toUserInfo(result.User),
		AccessToken:  result.AccessToken,
		RefreshToken: result.RefreshToken,
		ExpiresIn:    result.ExpiresIn,
	}, nil
}

func (s *AuthServer) RefreshToken(ctx context.Context, req *authv1.RefreshTokenRequest) (*authv1.RefreshTokenResponse, error) {
	result, err := s.svc.RefreshToken(ctx, req.GetRefreshToken())
	if err != nil {
		return &authv1.RefreshTokenResponse{Code: mapErrorCode(err), Message: publicAuthErrorMessage(err)}, nil
	}
	return &authv1.RefreshTokenResponse{
		Code: CodeSuccess, Message: "Token 刷新成功",
		AccessToken: result.AccessToken, RefreshToken: result.RefreshToken, ExpiresIn: result.ExpiresIn,
	}, nil
}

func (s *AuthServer) Logout(ctx context.Context, req *authv1.LogoutRequest) (*authv1.LogoutResponse, error) {
	if err := s.svc.Logout(ctx, req.GetRefreshToken()); err != nil {
		return &authv1.LogoutResponse{Code: mapErrorCode(err), Message: publicAuthErrorMessage(err)}, nil
	}
	return &authv1.LogoutResponse{Code: CodeSuccess, Message: "退出登录成功"}, nil
}

func (s *AuthServer) SendSMSCode(ctx context.Context, req *authv1.SendSMSCodeRequest) (*authv1.SendSMSCodeResponse, error) {
	result, err := s.svc.SendSMSCode(ctx, req.GetPhone(), req.GetClientIp())
	if err != nil {
		response := &authv1.SendSMSCodeResponse{Code: mapErrorCode(err), Message: publicAuthErrorMessage(err)}
		if result != nil {
			response.RetryAfterSeconds = result.RetryAfterSeconds
		}
		return response, nil
	}
	return &authv1.SendSMSCodeResponse{
		Code:              CodeSuccess,
		Message:           "验证码已发送",
		RetryAfterSeconds: result.RetryAfterSeconds,
	}, nil
}

func publicAuthErrorMessage(err error) string {
	if errors.Is(err, service.ErrSMSSendFailed) || errors.Is(err, service.ErrSMSUnavailable) {
		return service.ErrSMSUnavailable.Error()
	}
	if errors.Is(err, service.ErrSessionUnavailable) {
		return service.ErrSessionUnavailable.Error()
	}
	return err.Error()
}

// NewAuthServer 创建 AuthServer
func NewAuthServer(svc *service.AuthService) *AuthServer {
	return &AuthServer{svc: svc}
}

// Register 实现注册接口
func (s *AuthServer) Register(ctx context.Context, req *authv1.RegisterRequest) (*authv1.RegisterResponse, error) {
	result, err := s.svc.Register(ctx, req.Phone, req.Password, req.Nickname, req.DeviceId)
	if err != nil {
		return &authv1.RegisterResponse{
			Code:    mapErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &authv1.RegisterResponse{
		Code:         CodeSuccess,
		Message:      "注册成功",
		UserId:       int64(result.UserID),
		AccessToken:  result.AccessToken,
		RefreshToken: result.RefreshToken,
		ExpiresIn:    result.ExpiresIn,
		User:         toUserInfo(result.User),
	}, nil
}

// Login 实现登录接口
func (s *AuthServer) Login(ctx context.Context, req *authv1.LoginRequest) (*authv1.LoginResponse, error) {
	result, err := s.svc.Login(ctx, req.Phone, req.Password, req.DeviceId)
	if err != nil {
		return &authv1.LoginResponse{
			Code:    mapErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &authv1.LoginResponse{
		Code:         CodeSuccess,
		Message:      "登录成功",
		User:         toUserInfo(result.User),
		AccessToken:  result.AccessToken,
		RefreshToken: result.RefreshToken,
		ExpiresIn:    result.ExpiresIn,
	}, nil
}

// GetProfile 实现查询个人信息接口
func (s *AuthServer) GetProfile(ctx context.Context, req *authv1.GetProfileRequest) (*authv1.GetProfileResponse, error) {
	result, err := s.svc.GetProfile(ctx, uint64(req.UserId))
	if err != nil {
		return &authv1.GetProfileResponse{
			Code:    mapErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &authv1.GetProfileResponse{
		Code:       CodeSuccess,
		Message:    "查询成功",
		User:       toUserInfo(result.User),
		FamilyName: result.FamilyName,
	}, nil
}

// UpdateProfile 实现更新个人信息接口
func (s *AuthServer) UpdateProfile(ctx context.Context, req *authv1.UpdateProfileRequest) (*authv1.UpdateProfileResponse, error) {
	err := s.svc.UpdateProfile(ctx, uint64(req.UserId), req.Nickname, req.Avatar, req.Gender)
	if err != nil {
		return &authv1.UpdateProfileResponse{
			Code:    CodeInternalError,
			Message: err.Error(),
		}, nil
	}

	return &authv1.UpdateProfileResponse{
		Code:    CodeSuccess,
		Message: "更新成功",
	}, nil
}

// ListDietaryPreferences 查询当前用户保存的个人饮食偏好。
func (s *AuthServer) ListDietaryPreferences(ctx context.Context, req *authv1.ListDietaryPreferencesRequest) (*authv1.ListDietaryPreferencesResponse, error) {
	preferences, err := s.svc.ListDietaryPreferences(ctx, uint64(req.GetUserId()))
	if err != nil {
		return &authv1.ListDietaryPreferencesResponse{Code: mapErrorCode(err), Message: dietaryPreferenceErrorMessage(err)}, nil
	}
	return &authv1.ListDietaryPreferencesResponse{
		Code: CodeSuccess, Message: "查询成功", Preferences: toDietaryPreferenceInfos(preferences),
	}, nil
}

// ReplaceDietaryPreferences 整体替换当前用户的个人饮食偏好。
func (s *AuthServer) ReplaceDietaryPreferences(ctx context.Context, req *authv1.ReplaceDietaryPreferencesRequest) (*authv1.ReplaceDietaryPreferencesResponse, error) {
	inputs := make([]service.UserDietaryPreferenceInput, 0, len(req.GetPreferences()))
	for _, preference := range req.GetPreferences() {
		inputs = append(inputs, service.UserDietaryPreferenceInput{
			PreferenceType:  int8(preference.GetPreferenceType()),
			PreferenceValue: preference.GetPreferenceValue(),
			Note:            preference.GetNote(),
		})
	}
	preferences, err := s.svc.ReplaceDietaryPreferences(ctx, uint64(req.GetUserId()), inputs)
	if err != nil {
		return &authv1.ReplaceDietaryPreferencesResponse{Code: mapErrorCode(err), Message: dietaryPreferenceErrorMessage(err)}, nil
	}
	return &authv1.ReplaceDietaryPreferencesResponse{
		Code: CodeSuccess, Message: "保存成功", Preferences: toDietaryPreferenceInfos(preferences),
	}, nil
}

// dietaryPreferenceErrorMessage 只向客户端暴露可操作的偏好校验错误，隐藏数据库错误细节。
func dietaryPreferenceErrorMessage(err error) string {
	if errors.Is(err, service.ErrDietaryPreferenceUnavailable) ||
		errors.Is(err, service.ErrDietaryPreferenceType) ||
		errors.Is(err, service.ErrDietaryPreferenceValue) ||
		errors.Is(err, service.ErrDietaryPreferenceDuplicate) {
		return err.Error()
	}
	return "服务内部错误"
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
	case errors.Is(err, service.ErrPasswordNotSet):
		return CodePasswordNotSet
	case errors.Is(err, service.ErrUserDisabled):
		return CodeUserDisabled
	case errors.Is(err, service.ErrSMSCooldown):
		return CodeSMSCooldown
	case errors.Is(err, service.ErrSMSDailyLimit):
		return CodeSMSDailyLimit
	case errors.Is(err, service.ErrSMSIPLimit):
		return CodeSMSIPLimit
	case errors.Is(err, service.ErrSMSSendFailed):
		return CodeSMSSendFailed
	case errors.Is(err, service.ErrSMSUnavailable):
		return CodeSMSUnavailable
	case errors.Is(err, service.ErrSMSCodeInvalidOrExpired):
		return CodeSMSCodeInvalid
	case errors.Is(err, service.ErrSMSCodeAttemptsExceeded):
		return CodeSMSAttemptsLimit
	case errors.Is(err, service.ErrRefreshTokenInvalid):
		return CodeRefreshInvalid
	case errors.Is(err, service.ErrRefreshTokenReused):
		return CodeRefreshReused
	case errors.Is(err, service.ErrSessionUnavailable):
		return CodeSessionUnavailable
	case errors.Is(err, service.ErrDietaryPreferenceUnavailable):
		return CodeDietaryUnavailable
	case errors.Is(err, service.ErrDietaryPreferenceType):
		return CodeDietaryTypeInvalid
	case errors.Is(err, service.ErrDietaryPreferenceValue):
		return CodeDietaryValueInvalid
	case errors.Is(err, service.ErrDietaryPreferenceDuplicate):
		return CodeDietaryDuplicate
	default:
		return CodeInternalError
	}
}

// toDietaryPreferenceInfos 将个人饮食偏好业务结果转换为 Proto 列表。
func toDietaryPreferenceInfos(preferences []service.UserDietaryPreferenceResult) []*authv1.DietaryPreferenceInfo {
	result := make([]*authv1.DietaryPreferenceInfo, 0, len(preferences))
	for _, preference := range preferences {
		result = append(result, &authv1.DietaryPreferenceInfo{
			Id:              int64(preference.ID),
			PreferenceType:  int32(preference.PreferenceType),
			PreferenceValue: preference.PreferenceValue,
			Note:            preference.Note,
			CreatedAt:       preference.CreatedAt.Format("2006-01-02 15:04:05"),
			UpdatedAt:       preference.UpdatedAt.Format("2006-01-02 15:04:05"),
		})
	}
	return result
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
