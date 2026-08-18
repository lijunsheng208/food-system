package repository

import (
	"context"
	"errors"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

func TestRefreshSessionStoreWithRedis(t *testing.T) {
	addr := os.Getenv("FAMILYOS_TEST_REDIS_ADDR")
	if addr == "" {
		t.Skip("set FAMILYOS_TEST_REDIS_ADDR to run Redis integration test")
	}
	client := redis.NewClient(&redis.Options{Addr: addr, Password: os.Getenv("FAMILYOS_TEST_REDIS_PASSWORD")})
	t.Cleanup(func() { _ = client.Close() })
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		t.Fatalf("Redis Ping failed: %v", err)
	}

	store := NewRefreshSessionStore(client, "familyos:test:session")
	session := RefreshSession{UserID: 900001, Phone: "13800138000", SessionID: "integration-session", DeviceID: "test-device"}
	sessionKey := store.sessionKey(session.SessionID)
	userKey := store.userSessionsKey(session.UserID)
	t.Cleanup(func() { _ = client.Del(context.Background(), sessionKey, userKey).Err() })
	_ = client.Del(ctx, sessionKey, userKey).Err()

	if err := store.Create(ctx, session, "old-secret-hash", time.Hour); err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	fields, err := client.HGetAll(ctx, sessionKey).Result()
	if err != nil || fields["secret_hash"] != "old-secret-hash" || fields["device_id"] != "test-device" {
		t.Fatalf("stored session = %+v, error = %v", fields, err)
	}
	if ttl := client.TTL(ctx, sessionKey).Val(); ttl <= 59*time.Minute || ttl > time.Hour {
		t.Fatalf("session TTL = %v, want about 1 hour before rotation", ttl)
	}
	previousRefreshAt := fields["last_refresh_at"]
	time.Sleep(time.Millisecond)

	rotated, err := store.Rotate(ctx, session.SessionID, "old-secret-hash", "new-secret-hash", 30*24*time.Hour)
	if err != nil || rotated.UserID != session.UserID || rotated.DeviceID != session.DeviceID {
		t.Fatalf("Rotate() = %+v, %v", rotated, err)
	}
	rotatedFields, err := client.HGetAll(ctx, sessionKey).Result()
	if err != nil || rotatedFields["secret_hash"] != "new-secret-hash" || rotatedFields["last_refresh_at"] == previousRefreshAt {
		t.Fatalf("rotated session = %+v, error = %v", rotatedFields, err)
	}
	if ttl := client.TTL(ctx, sessionKey).Val(); ttl <= 29*24*time.Hour || ttl > 30*24*time.Hour {
		t.Fatalf("rotated session TTL = %v, want about 30 days", ttl)
	}
	if _, err := store.Rotate(ctx, session.SessionID, "old-secret-hash", "another-secret-hash", 30*24*time.Hour); !errors.Is(err, ErrRefreshTokenReused) {
		t.Fatalf("old token replay error = %v, want ErrRefreshTokenReused", err)
	}

	if err := store.Revoke(ctx, session.UserID, session.SessionID, "new-secret-hash"); err != nil {
		t.Fatalf("Revoke() error = %v", err)
	}
	if client.Exists(ctx, sessionKey).Val() != 0 || client.Exists(ctx, userKey).Val() != 0 {
		t.Fatal("session or user session index remains after revoke")
	}
}

func TestRefreshSessionRotationIsAtomicWithRedis(t *testing.T) {
	addr := os.Getenv("FAMILYOS_TEST_REDIS_ADDR")
	if addr == "" {
		t.Skip("set FAMILYOS_TEST_REDIS_ADDR to run Redis integration test")
	}
	client := redis.NewClient(&redis.Options{Addr: addr, Password: os.Getenv("FAMILYOS_TEST_REDIS_PASSWORD")})
	t.Cleanup(func() { _ = client.Close() })
	store := NewRefreshSessionStore(client, "familyos:test:session-race")
	ctx := context.Background()
	session := RefreshSession{UserID: 900002, Phone: "13800138001", SessionID: "race-session"}
	t.Cleanup(func() {
		_ = client.Del(ctx, store.sessionKey(session.SessionID), store.userSessionsKey(session.UserID)).Err()
	})
	_ = client.Del(ctx, store.sessionKey(session.SessionID), store.userSessionsKey(session.UserID)).Err()
	if err := store.Create(ctx, session, "shared-old-hash", time.Hour); err != nil {
		t.Fatalf("Create() error = %v", err)
	}

	errs := make(chan error, 2)
	var wg sync.WaitGroup
	wg.Add(2)
	for _, nextHash := range []string{"next-a", "next-b"} {
		go func(hash string) {
			defer wg.Done()
			_, err := store.Rotate(ctx, session.SessionID, "shared-old-hash", hash, time.Hour)
			errs <- err
		}(nextHash)
	}
	wg.Wait()
	close(errs)
	success, replay := 0, 0
	for err := range errs {
		if err == nil {
			success++
		} else if errors.Is(err, ErrRefreshTokenReused) {
			replay++
		} else {
			t.Fatalf("unexpected rotation error: %v", err)
		}
	}
	if success != 1 || replay != 1 {
		t.Fatalf("success=%d replay=%d, want 1 and 1", success, replay)
	}
}
