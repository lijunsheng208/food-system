package service

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
	pkgjwt "github.com/lijunsheng/familyos/pkg/jwt"
)

var (
	ErrRefreshTokenInvalid = errors.New("Refresh Token 无效或已过期")
	ErrRefreshTokenReused  = errors.New("Refresh Token 已失效或被重复使用")
	ErrSessionUnavailable  = errors.New("登录会话服务暂不可用")
)

type RefreshSessionStore interface {
	Create(ctx context.Context, session repository.RefreshSession, secretHash string, ttl time.Duration) error
	Rotate(ctx context.Context, sessionID, oldSecretHash, newSecretHash string, ttl time.Duration) (*repository.RefreshSession, error)
	Revoke(ctx context.Context, userID uint64, sessionID, secretHash string) error
	Delete(ctx context.Context, userID uint64, sessionID string) error
	UserID(ctx context.Context, sessionID string) (uint64, error)
}

type TokenConfig struct {
	Issuer     string
	Audience   string
	AccessTTL  time.Duration
	RefreshTTL time.Duration
}

type TokenPair struct {
	AccessToken  string
	RefreshToken string
	ExpiresIn    int32
}

func (s *AuthService) ConfigureTokens(store RefreshSessionStore, cfg TokenConfig) {
	s.sessionStore = store
	s.tokenConfig = cfg
}

func (s *AuthService) issueTokenPair(ctx context.Context, user *model.User, deviceID string) (*TokenPair, error) {
	if s.sessionStore == nil || s.tokenConfig.AccessTTL <= 0 || s.tokenConfig.RefreshTTL <= 0 {
		return nil, ErrSessionUnavailable
	}
	for range 3 {
		sessionID, err := randomTokenPart(16)
		if err != nil {
			return nil, err
		}
		secret, err := randomTokenPart(32)
		if err != nil {
			return nil, err
		}
		session := repository.RefreshSession{UserID: user.ID, Phone: user.Phone, SessionID: sessionID, DeviceID: deviceID}
		if err := s.sessionStore.Create(ctx, session, hashRefreshSecret(secret), s.tokenConfig.RefreshTTL); err != nil {
			continue
		}
		pair, err := s.accessAndRefreshTokens(user, sessionID, secret)
		if err != nil {
			_ = s.sessionStore.Delete(ctx, user.ID, sessionID)
			return nil, err
		}
		return pair, nil
	}
	return nil, ErrSessionUnavailable
}

func (s *AuthService) accessAndRefreshTokens(user *model.User, sessionID, refreshSecret string) (*TokenPair, error) {
	tokenID, err := randomTokenPart(16)
	if err != nil {
		return nil, err
	}
	accessToken, err := pkgjwt.GenerateAccessToken(
		s.jwtSecret, s.tokenConfig.Issuer, s.tokenConfig.Audience,
		user.ID, user.Phone, sessionID, tokenID, s.tokenConfig.AccessTTL,
	)
	if err != nil {
		return nil, err
	}
	return &TokenPair{
		AccessToken:  accessToken,
		RefreshToken: sessionID + "." + refreshSecret,
		ExpiresIn:    durationSeconds(s.tokenConfig.AccessTTL),
	}, nil
}

func (s *AuthService) RefreshToken(ctx context.Context, refreshToken string) (*TokenPair, error) {
	if s.sessionStore == nil {
		return nil, ErrSessionUnavailable
	}
	sessionID, oldSecret, err := parseRefreshToken(refreshToken)
	if err != nil {
		return nil, ErrRefreshTokenInvalid
	}
	newSecret, err := randomTokenPart(32)
	if err != nil {
		return nil, err
	}
	session, err := s.sessionStore.Rotate(ctx, sessionID, hashRefreshSecret(oldSecret), hashRefreshSecret(newSecret), s.tokenConfig.RefreshTTL)
	if err != nil {
		return nil, mapRefreshSessionError(err)
	}
	user, err := s.userRepo.FindByID(ctx, session.UserID)
	if err != nil {
		return nil, err
	}
	if user == nil {
		return nil, ErrRefreshTokenInvalid
	}
	if user.Status == model.UserStatusDisabled {
		return nil, ErrUserDisabled
	}
	return s.accessAndRefreshTokens(user, sessionID, newSecret)
}

func (s *AuthService) Logout(ctx context.Context, refreshToken string) error {
	if s.sessionStore == nil {
		return ErrSessionUnavailable
	}
	sessionID, secret, err := parseRefreshToken(refreshToken)
	if err != nil {
		return ErrRefreshTokenInvalid
	}
	userID, err := s.sessionStore.UserID(ctx, sessionID)
	if err != nil {
		return mapRefreshSessionError(err)
	}
	if err := s.sessionStore.Revoke(ctx, userID, sessionID, hashRefreshSecret(secret)); err != nil {
		return mapRefreshSessionError(err)
	}
	return nil
}

func mapRefreshSessionError(err error) error {
	switch {
	case errors.Is(err, repository.ErrRefreshSessionNotFound):
		return ErrRefreshTokenInvalid
	case errors.Is(err, repository.ErrRefreshTokenReused):
		return ErrRefreshTokenReused
	default:
		return fmt.Errorf("%w: %v", ErrSessionUnavailable, err)
	}
}

func parseRefreshToken(token string) (string, string, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "", "", ErrRefreshTokenInvalid
	}
	sessionIDBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil || len(sessionIDBytes) != 16 {
		return "", "", ErrRefreshTokenInvalid
	}
	secretBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil || len(secretBytes) != 32 {
		return "", "", ErrRefreshTokenInvalid
	}
	return parts[0], parts[1], nil
}

func randomTokenPart(size int) (string, error) {
	value := make([]byte, size)
	if _, err := rand.Read(value); err != nil {
		return "", fmt.Errorf("生成安全随机 Token 失败: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(value), nil
}

func hashRefreshSecret(secret string) string {
	digest := sha256.Sum256([]byte(secret))
	return hex.EncodeToString(digest[:])
}
