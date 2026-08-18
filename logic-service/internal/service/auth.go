package service

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
	"github.com/lijunsheng/familyos/pkg/password"
)

// 业务错误
var (
	ErrPhoneAlreadyExists = errors.New("手机号已注册")
	ErrUserNotFound       = errors.New("用户不存在")
	ErrPasswordWrong      = errors.New("密码错误")
	ErrUserDisabled       = errors.New("用户已被禁用")
	ErrInvalidPhone       = errors.New("手机号格式不正确")
	ErrPasswordTooShort   = errors.New("密码长度不能少于6位")
	ErrPasswordNotSet     = errors.New("该账号尚未设置密码，请使用验证码登录")
)

// AuthService 认证业务逻辑
type AuthService struct {
	userRepo     *repository.UserRepo
	familyRepo   *repository.FamilyRepo
	jwtSecret    string
	smsStore     SMSCodeStore
	smsSender    SMSProvider
	smsConfig    SMSCodeConfig
	sessionStore RefreshSessionStore
	tokenConfig  TokenConfig
}

func (s *AuthService) ConfigureSMS(store SMSCodeStore, sender SMSProvider, cfg SMSCodeConfig) {
	s.smsStore = store
	s.smsSender = sender
	s.smsConfig = cfg
}

// NewAuthService 创建 AuthService
func NewAuthService(userRepo *repository.UserRepo, familyRepo *repository.FamilyRepo, jwtSecret string) *AuthService {
	return &AuthService{
		userRepo:   userRepo,
		familyRepo: familyRepo,
		jwtSecret:  jwtSecret,
	}
}

// RegisterResult 注册结果
type RegisterResult struct {
	UserID uint64
	User   *model.User
	*TokenPair
}

// Register 用户注册
func (s *AuthService) Register(ctx context.Context, phone, plainPassword, nickname, deviceID string) (*RegisterResult, error) {
	// 1. 校验手机号
	if !isValidPhone(phone) {
		return nil, ErrInvalidPhone
	}

	// 2. 校验密码长度
	if len(plainPassword) < 6 {
		return nil, ErrPasswordTooShort
	}

	// 3. 查重
	existing, err := s.userRepo.FindByPhone(ctx, phone)
	if err != nil {
		return nil, err
	}
	if existing != nil {
		return nil, ErrPhoneAlreadyExists
	}

	// 4. 密码哈希
	hashedPwd, err := password.Hash(plainPassword)
	if err != nil {
		return nil, err
	}

	// 5. 写入数据库
	user := &model.User{
		Phone:        phone,
		PasswordHash: &hashedPwd,
		Nickname:     nickname,
	}
	if err := s.userRepo.Create(ctx, user); err != nil {
		return nil, err
	}

	// 6. 创建登录会话并签发 Token
	tokens, err := s.issueTokenPair(ctx, user, deviceID)
	if err != nil {
		return nil, err
	}

	return &RegisterResult{
		UserID:    user.ID,
		User:      user,
		TokenPair: tokens,
	}, nil
}

// GetProfileResult 个人信息结果
type GetProfileResult struct {
	User       *model.User
	FamilyName string
}

// GetProfile 查询用户个人信息
func (s *AuthService) GetProfile(ctx context.Context, userID uint64) (*GetProfileResult, error) {
	user, err := s.userRepo.FindByID(ctx, userID)
	if err != nil {
		return nil, err
	}
	if user == nil {
		return nil, ErrUserNotFound
	}

	// 查询用户所属家庭
	familyName := ""
	if s.familyRepo != nil {
		member, err := s.familyRepo.GetMemberByUserID(ctx, userID)
		if err == nil && member != nil {
			family, err := s.familyRepo.GetFamilyByID(ctx, member.FamilyID)
			if err == nil && family != nil && family.Status == model.FamilyStatusNormal {
				familyName = family.Name
			}
		}
	}

	return &GetProfileResult{
		User:       user,
		FamilyName: familyName,
	}, nil
}

// UpdateProfile 更新用户个人信息
func (s *AuthService) UpdateProfile(ctx context.Context, userID uint64, nickname, avatar string, gender int32) error {
	updates := make(map[string]interface{})

	if nickname != "" {
		updates["nickname"] = nickname
	}
	if avatar != "" {
		updates["avatar"] = avatar
	}
	if gender >= 0 {
		updates["gender"] = int8(gender)
	}

	if len(updates) == 0 {
		return nil
	}

	return s.userRepo.UpdateProfile(ctx, userID, updates)
}

// LoginResult 登录结果
type LoginResult struct {
	User *model.User
	*TokenPair
}

// Login 用户登录
func (s *AuthService) Login(ctx context.Context, phone, plainPassword, deviceID string) (*LoginResult, error) {
	// 1. 校验手机号
	if !isValidPhone(phone) {
		return nil, ErrInvalidPhone
	}

	// 2. 查询用户
	user, err := s.userRepo.FindByPhone(ctx, phone)
	if err != nil {
		return nil, err
	}
	if user == nil {
		return nil, ErrUserNotFound
	}

	// 3. 验证密码
	if user.PasswordHash == nil {
		return nil, ErrPasswordNotSet
	}
	if !password.Verify(*user.PasswordHash, plainPassword) {
		return nil, ErrPasswordWrong
	}

	// 4. 检查状态
	if user.Status == model.UserStatusDisabled {
		return nil, ErrUserDisabled
	}

	// 5. 更新最后登录时间
	if err := s.userRepo.UpdateLastLogin(ctx, user.ID); err != nil {
		return nil, err
	}

	// 6. 创建登录会话并签发 Token
	tokens, err := s.issueTokenPair(ctx, user, deviceID)
	if err != nil {
		return nil, err
	}

	return &LoginResult{
		User:      user,
		TokenPair: tokens,
	}, nil
}

// SMSLoginResult 短信验证码登录结果。
type SMSLoginResult struct {
	User      *model.User
	IsNewUser bool
	*TokenPair
}

// SMSLogin 使用一次性短信验证码登录，手机号不存在时自动注册。
func (s *AuthService) SMSLogin(ctx context.Context, phone, verificationCode, deviceID string) (*SMSLoginResult, error) {
	if !isValidPhone(phone) {
		return nil, ErrInvalidPhone
	}
	if err := s.VerifySMSCode(ctx, phone, verificationCode); err != nil {
		return nil, err
	}

	user, err := s.userRepo.FindByPhone(ctx, phone)
	if err != nil {
		return nil, err
	}
	isNewUser := false
	if user == nil {
		user = &model.User{
			Phone:    phone,
			Nickname: "用户" + phone[len(phone)-4:],
			Status:   model.UserStatusNormal,
		}
		if err := s.userRepo.Create(ctx, user); err != nil {
			if !repository.IsDuplicateKeyError(err) {
				return nil, err
			}
			user, err = s.userRepo.FindByPhone(ctx, phone)
			if err != nil {
				return nil, err
			}
			if user == nil {
				return nil, fmt.Errorf("唯一键冲突后未查询到用户")
			}
		} else {
			isNewUser = true
		}
	}
	if user.Status == model.UserStatusDisabled {
		return nil, ErrUserDisabled
	}
	if err := s.userRepo.UpdateLastLogin(ctx, user.ID); err != nil {
		return nil, err
	}
	now := time.Now()
	user.LastLoginAt = &now

	tokens, err := s.issueTokenPair(ctx, user, deviceID)
	if err != nil {
		return nil, err
	}
	return &SMSLoginResult{User: user, IsNewUser: isNewUser, TokenPair: tokens}, nil
}

// isValidPhone 简单校验手机号格式
func isValidPhone(phone string) bool {
	matched, _ := regexp.MatchString(`^1[3-9]\d{9}$`, phone)
	return matched
}
