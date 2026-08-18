package repository

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

var (
	ErrSMSCooldown             = errors.New("验证码发送过于频繁")
	ErrSMSDailyLimit           = errors.New("该手机号今日发送次数已达上限")
	ErrSMSIPLimit              = errors.New("当前网络发送次数过多")
	ErrSMSCodeInvalidOrExpired = errors.New("验证码无效或已过期")
	ErrSMSCodeAttemptsExceeded = errors.New("验证码错误次数过多")
)

type SMSCodeStore struct {
	client *redis.Client
	prefix string
}

func NewSMSCodeStore(client *redis.Client, prefix string) *SMSCodeStore {
	return &SMSCodeStore{client: client, prefix: strings.TrimSuffix(prefix, ":")}
}

var reserveSMSCodeScript = redis.NewScript(`
if redis.call('EXISTS', KEYS[2]) == 1 then
  return {1, redis.call('TTL', KEYS[2])}
end
local daily = tonumber(redis.call('GET', KEYS[3]) or '0')
if daily >= tonumber(ARGV[5]) then
  return {2, redis.call('TTL', KEYS[3])}
end
local ip_count = tonumber(redis.call('GET', KEYS[4]) or '0')
if ip_count >= tonumber(ARGV[7]) then
  return {3, redis.call('TTL', KEYS[4])}
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
redis.call('SET', KEYS[2], ARGV[8], 'EX', ARGV[3])
local new_daily = redis.call('INCR', KEYS[3])
if new_daily == 1 then redis.call('EXPIRE', KEYS[3], ARGV[4]) end
local new_ip = redis.call('INCR', KEYS[4])
if new_ip == 1 then redis.call('EXPIRE', KEYS[4], ARGV[6]) end
return {0, tonumber(ARGV[3])}
`)

var rollbackSMSCodeScript = redis.NewScript(`
if redis.call('GET', KEYS[2]) ~= ARGV[1] then return 0 end
redis.call('DEL', KEYS[1], KEYS[2])
local daily = redis.call('DECR', KEYS[3])
if daily <= 0 then redis.call('DEL', KEYS[3]) end
local ip_count = redis.call('DECR', KEYS[4])
if ip_count <= 0 then redis.call('DEL', KEYS[4]) end
return 1
`)

var verifySMSCodeScript = redis.NewScript(`
local stored = redis.call('GET', KEYS[1])
if not stored then return 1 end
local failures = tonumber(redis.call('GET', KEYS[2]) or '0')
if failures >= tonumber(ARGV[2]) then return 2 end
if stored ~= ARGV[1] then
  failures = redis.call('INCR', KEYS[2])
  local ttl = redis.call('TTL', KEYS[1])
  if ttl > 0 then redis.call('EXPIRE', KEYS[2], ttl) end
  if failures >= tonumber(ARGV[2]) then return 2 end
  return 1
end
redis.call('DEL', KEYS[1], KEYS[2])
return 0
`)

func (s *SMSCodeStore) ReserveLoginCode(
	ctx context.Context,
	phone, clientIP, digest, reservationID, dailyBucket string,
	codeTTL, cooldown, dailyTTL, ipWindow time.Duration,
	dailyLimit, ipLimit int64,
) (time.Duration, error) {
	keys := s.keys(phone, clientIP, dailyBucket)
	result, err := reserveSMSCodeScript.Run(ctx, s.client, keys,
		digest,
		seconds(codeTTL),
		seconds(cooldown),
		seconds(dailyTTL),
		dailyLimit,
		seconds(ipWindow),
		ipLimit,
		reservationID,
	).Int64Slice()
	if err != nil {
		return 0, err
	}
	if len(result) != 2 {
		return 0, fmt.Errorf("Redis 验证码限流脚本返回异常")
	}
	retryAfter := time.Duration(max(result[1], 1)) * time.Second
	switch result[0] {
	case 0:
		return retryAfter, nil
	case 1:
		return retryAfter, ErrSMSCooldown
	case 2:
		return retryAfter, ErrSMSDailyLimit
	case 3:
		return retryAfter, ErrSMSIPLimit
	default:
		return 0, fmt.Errorf("Redis 验证码限流脚本状态异常: %d", result[0])
	}
}

func (s *SMSCodeStore) RollbackLoginCode(ctx context.Context, phone, clientIP, reservationID, dailyBucket string) error {
	keys := s.keys(phone, clientIP, dailyBucket)
	return rollbackSMSCodeScript.Run(ctx, s.client, keys, reservationID).Err()
}

// VerifyLoginCode 原子校验并消费登录验证码。
func (s *SMSCodeStore) VerifyLoginCode(ctx context.Context, phone, digest string, maxAttempts int64) error {
	phoneTag := "{" + phone + "}"
	keys := []string{
		s.prefix + ":sms:" + phoneTag + ":code",
		s.prefix + ":sms:" + phoneTag + ":failures",
	}
	result, err := verifySMSCodeScript.Run(ctx, s.client, keys, digest, maxAttempts).Int64()
	if err != nil {
		return err
	}
	switch result {
	case 0:
		return nil
	case 1:
		return ErrSMSCodeInvalidOrExpired
	case 2:
		return ErrSMSCodeAttemptsExceeded
	default:
		return fmt.Errorf("Redis 验证码校验脚本状态异常: %d", result)
	}
}

func (s *SMSCodeStore) keys(phone, clientIP, dailyBucket string) []string {
	phoneTag := "{" + phone + "}"
	ip := strings.NewReplacer(":", "_", "%", "_").Replace(clientIP)
	return []string{
		s.prefix + ":sms:" + phoneTag + ":code",
		s.prefix + ":sms:" + phoneTag + ":cooldown",
		s.prefix + ":sms:" + phoneTag + ":daily:" + dailyBucket,
		s.prefix + ":sms:ip:" + ip + ":window",
	}
}

func seconds(value time.Duration) int64 {
	result := int64(value / time.Second)
	if result < 1 {
		return 1
	}
	return result
}
