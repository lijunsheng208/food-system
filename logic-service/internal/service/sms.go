package service

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"math/big"
	"net"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/repository"
)

var (
	ErrSMSCooldown             = repository.ErrSMSCooldown
	ErrSMSDailyLimit           = repository.ErrSMSDailyLimit
	ErrSMSIPLimit              = repository.ErrSMSIPLimit
	ErrSMSSendFailed           = errors.New("短信发送失败")
	ErrSMSUnavailable          = errors.New("短信验证码服务暂不可用")
	ErrSMSCodeInvalidOrExpired = repository.ErrSMSCodeInvalidOrExpired
	ErrSMSCodeAttemptsExceeded = repository.ErrSMSCodeAttemptsExceeded
)

type SMSCodeStore interface {
	ReserveLoginCode(
		ctx context.Context,
		phone, clientIP, digest, reservationID, dailyBucket string,
		codeTTL, cooldown, dailyTTL, ipWindow time.Duration,
		dailyLimit, ipLimit int64,
	) (time.Duration, error)
	RollbackLoginCode(ctx context.Context, phone, clientIP, reservationID, dailyBucket string) error
	VerifyLoginCode(ctx context.Context, phone, digest string, maxAttempts int64) error
}

const maxSMSCodeAttempts int64 = 5

// VerifySMSCode 校验并一次性消费短信验证码。
func (s *AuthService) VerifySMSCode(ctx context.Context, phone, code string) error {
	if !isValidPhone(phone) || len(code) != 6 {
		return ErrSMSCodeInvalidOrExpired
	}
	if s.smsStore == nil || s.smsConfig.HMACSecret == "" {
		return ErrSMSUnavailable
	}
	digest := digestSMSCode(s.smsConfig.HMACSecret, phone, code)
	if err := s.smsStore.VerifyLoginCode(ctx, phone, digest, maxSMSCodeAttempts); err != nil {
		if errors.Is(err, ErrSMSCodeInvalidOrExpired) || errors.Is(err, ErrSMSCodeAttemptsExceeded) {
			return err
		}
		return fmt.Errorf("%w: %v", ErrSMSUnavailable, err)
	}
	return nil
}

type SMSProvider interface {
	SendLoginCode(ctx context.Context, phone, code string) error
}

type SMSCodeConfig struct {
	HMACSecret    string
	CodeTTL       time.Duration
	Cooldown      time.Duration
	DailyLimit    int64
	IPLimit       int64
	IPLimitWindow time.Duration
}

type SendSMSCodeResult struct {
	RetryAfterSeconds int32
}

func (s *AuthService) SendSMSCode(ctx context.Context, phone, clientIP string) (*SendSMSCodeResult, error) {
	if !isValidPhone(phone) {
		return nil, ErrInvalidPhone
	}
	if s.smsStore == nil || s.smsSender == nil || s.smsConfig.HMACSecret == "" {
		return nil, ErrSMSUnavailable
	}
	if net.ParseIP(clientIP) == nil {
		clientIP = "unknown"
	}

	// 生成六位验证码
	code, err := generateSMSCode()
	if err != nil {
		return nil, err
	}

	// 生成本次发送请求的唯一标识，用于在发送失败时回滚预留
	reservationID, err := generateReservationID()
	if err != nil {
		return nil, err
	}

	now := time.Now()
	dailyBucket := now.Format("20060102")
	dailyTTL := untilEndOfDay(now)
	digest := digestSMSCode(s.smsConfig.HMACSecret, phone, code)

	// 原子预留验证码发送请求
	retryAfter, err := s.smsStore.ReserveLoginCode(
		ctx,
		phone,
		clientIP,
		digest,
		reservationID,
		dailyBucket,
		s.smsConfig.CodeTTL,
		s.smsConfig.Cooldown,
		dailyTTL,
		s.smsConfig.IPLimitWindow,
		s.smsConfig.DailyLimit,
		s.smsConfig.IPLimit,
	)
	if err != nil {
		result := &SendSMSCodeResult{RetryAfterSeconds: durationSeconds(retryAfter)}
		if errors.Is(err, ErrSMSCooldown) || errors.Is(err, ErrSMSDailyLimit) || errors.Is(err, ErrSMSIPLimit) {
			return result, err
		}
		return result, fmt.Errorf("%w: %v", ErrSMSUnavailable, err)
	}

	if err := s.smsSender.SendLoginCode(ctx, phone, code); err != nil {
		rollbackCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = s.smsStore.RollbackLoginCode(rollbackCtx, phone, clientIP, reservationID, dailyBucket)
		return nil, fmt.Errorf("%w: %v", ErrSMSSendFailed, err)
	}

	return &SendSMSCodeResult{RetryAfterSeconds: durationSeconds(retryAfter)}, nil
}

func generateSMSCode() (string, error) {
	value, err := rand.Int(rand.Reader, big.NewInt(1_000_000))
	if err != nil {
		return "", fmt.Errorf("生成短信验证码失败: %w", err)
	}
	return fmt.Sprintf("%06d", value.Int64()), nil
}

func generateReservationID() (string, error) {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		return "", fmt.Errorf("生成验证码预留标识失败: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(value), nil
}

func digestSMSCode(secret, phone, code string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(phone + ":" + code))
	return hex.EncodeToString(mac.Sum(nil))
}

func untilEndOfDay(now time.Time) time.Duration {
	nextDay := time.Date(now.Year(), now.Month(), now.Day()+1, 0, 0, 0, 0, now.Location())
	result := nextDay.Sub(now)
	if result < time.Second {
		return time.Second
	}
	return result
}

func durationSeconds(value time.Duration) int32 {
	seconds := int64(value / time.Second)
	if seconds < 1 {
		seconds = 1
	}
	if seconds > int64(^uint32(0)>>1) {
		seconds = int64(^uint32(0) >> 1)
	}
	return int32(seconds)
}
