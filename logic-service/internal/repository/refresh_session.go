package repository

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
)

var (
	ErrRefreshSessionNotFound = errors.New("Refresh Session 不存在或已过期")
	ErrRefreshTokenReused     = errors.New("Refresh Token 已失效或被重复使用")
)

type RefreshSession struct {
	UserID    uint64
	Phone     string
	SessionID string
	DeviceID  string
}

type RefreshSessionStore struct {
	client *redis.Client
	prefix string
}

func NewRefreshSessionStore(client *redis.Client, prefix string) *RefreshSessionStore {
	return &RefreshSessionStore{client: client, prefix: strings.TrimSuffix(prefix, ":")}
}

var createRefreshSessionScript = redis.NewScript(`
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
redis.call('HSET', KEYS[1],
  'user_id', ARGV[1],
  'phone', ARGV[2],
  'device_id', ARGV[3],
  'secret_hash', ARGV[4],
  'created_at', ARGV[5],
  'last_refresh_at', ARGV[5])
redis.call('EXPIRE', KEYS[1], ARGV[6])
redis.call('SADD', KEYS[2], ARGV[7])
redis.call('EXPIRE', KEYS[2], ARGV[6])
return 1
`)

var rotateRefreshSessionScript = redis.NewScript(`
local stored = redis.call('HGET', KEYS[1], 'secret_hash')
if not stored then return {'1'} end
if stored ~= ARGV[1] then return {'2'} end
local user_id = redis.call('HGET', KEYS[1], 'user_id')
local phone = redis.call('HGET', KEYS[1], 'phone')
local device_id = redis.call('HGET', KEYS[1], 'device_id') or ''
redis.call('HSET', KEYS[1], 'secret_hash', ARGV[2], 'last_refresh_at', ARGV[3])
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[4])
return {'0', user_id, phone, device_id}
`)

var deleteRefreshSessionScript = redis.NewScript(`
local stored = redis.call('HGET', KEYS[1], 'secret_hash')
if not stored then return 1 end
if stored ~= ARGV[2] then return 2 end
redis.call('DEL', KEYS[1])
redis.call('SREM', KEYS[2], ARGV[1])
if redis.call('SCARD', KEYS[2]) == 0 then redis.call('DEL', KEYS[2]) end
return 0
`)

var cleanupRefreshSessionScript = redis.NewScript(`
redis.call('DEL', KEYS[1])
redis.call('SREM', KEYS[2], ARGV[1])
if redis.call('SCARD', KEYS[2]) == 0 then redis.call('DEL', KEYS[2]) end
return 1
`)

func (s *RefreshSessionStore) Create(ctx context.Context, session RefreshSession, secretHash string, ttl time.Duration) error {
	createdAt := time.Now().UTC().Format(time.RFC3339Nano)
	result, err := createRefreshSessionScript.Run(ctx, s.client, []string{
		s.sessionKey(session.SessionID), s.userSessionsKey(session.UserID),
	}, session.UserID, session.Phone, session.DeviceID, secretHash, createdAt, seconds(ttl), session.SessionID).Int64()
	if err != nil {
		return err
	}
	if result != 1 {
		return fmt.Errorf("Refresh Session ID 冲突")
	}
	return nil
}

func (s *RefreshSessionStore) Rotate(ctx context.Context, sessionID, oldSecretHash, newSecretHash string, ttl time.Duration) (*RefreshSession, error) {
	userIDValue, err := s.client.HGet(ctx, s.sessionKey(sessionID), "user_id").Result()
	if errors.Is(err, redis.Nil) {
		return nil, ErrRefreshSessionNotFound
	}
	if err != nil {
		return nil, err
	}
	userID, err := strconv.ParseUint(userIDValue, 10, 64)
	if err != nil {
		return nil, fmt.Errorf("Refresh Session user_id 无效: %w", err)
	}

	result, err := rotateRefreshSessionScript.Run(ctx, s.client, []string{
		s.sessionKey(sessionID), s.userSessionsKey(userID),
	}, oldSecretHash, newSecretHash, time.Now().UTC().Format(time.RFC3339Nano), seconds(ttl)).StringSlice()
	if err != nil {
		return nil, err
	}
	if len(result) == 0 {
		return nil, fmt.Errorf("Redis Refresh Rotation 脚本返回异常")
	}
	switch result[0] {
	case "1":
		return nil, ErrRefreshSessionNotFound
	case "2":
		return nil, ErrRefreshTokenReused
	case "0":
		if len(result) != 4 {
			return nil, fmt.Errorf("Redis Refresh Rotation 脚本返回字段异常")
		}
		rotatedUserID, err := strconv.ParseUint(result[1], 10, 64)
		if err != nil {
			return nil, fmt.Errorf("Refresh Session user_id 无效: %w", err)
		}
		return &RefreshSession{UserID: rotatedUserID, Phone: result[2], SessionID: sessionID, DeviceID: result[3]}, nil
	default:
		return nil, fmt.Errorf("Redis Refresh Rotation 脚本状态异常: %s", result[0])
	}
}

func (s *RefreshSessionStore) Revoke(ctx context.Context, userID uint64, sessionID, secretHash string) error {
	result, err := deleteRefreshSessionScript.Run(ctx, s.client, []string{
		s.sessionKey(sessionID), s.userSessionsKey(userID),
	}, sessionID, secretHash).Int64()
	if err != nil {
		return err
	}
	switch result {
	case 0:
		return nil
	case 1:
		return ErrRefreshSessionNotFound
	case 2:
		return ErrRefreshTokenReused
	default:
		return fmt.Errorf("Redis Refresh Revoke 脚本状态异常: %d", result)
	}
}

func (s *RefreshSessionStore) Delete(ctx context.Context, userID uint64, sessionID string) error {
	return cleanupRefreshSessionScript.Run(ctx, s.client, []string{
		s.sessionKey(sessionID), s.userSessionsKey(userID),
	}, sessionID).Err()
}

func (s *RefreshSessionStore) UserID(ctx context.Context, sessionID string) (uint64, error) {
	value, err := s.client.HGet(ctx, s.sessionKey(sessionID), "user_id").Result()
	if errors.Is(err, redis.Nil) {
		return 0, ErrRefreshSessionNotFound
	}
	if err != nil {
		return 0, err
	}
	userID, err := strconv.ParseUint(value, 10, 64)
	if err != nil {
		return 0, fmt.Errorf("Refresh Session user_id 无效: %w", err)
	}
	return userID, nil
}

func (s *RefreshSessionStore) sessionKey(sessionID string) string {
	return s.prefix + ":refresh:" + sessionID
}

func (s *RefreshSessionStore) userSessionsKey(userID uint64) string {
	return s.prefix + ":user_sessions:" + strconv.FormatUint(userID, 10)
}
