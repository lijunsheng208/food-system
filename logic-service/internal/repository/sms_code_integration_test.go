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

func TestSMSCodeStoreWithRedis(t *testing.T) {
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

	store := NewSMSCodeStore(client, "familyos:test:sms")
	phone := "13800138000"
	ip := "127.0.0.1"
	bucket := "20990101"
	keys := store.keys(phone, ip, bucket)
	t.Cleanup(func() { _ = client.Del(context.Background(), keys...).Err() })
	if err := client.Del(ctx, keys...).Err(); err != nil {
		t.Fatalf("cleanup test keys: %v", err)
	}

	retryAfter, err := store.ReserveLoginCode(
		ctx, phone, ip, "hmac-digest", "reservation-1", bucket,
		5*time.Minute, time.Minute, time.Hour, time.Hour, 10, 30,
	)
	if err != nil {
		t.Fatalf("first ReserveLoginCode() error = %v", err)
	}
	if retryAfter != time.Minute {
		t.Fatalf("retry_after = %v, want 1m", retryAfter)
	}
	stored, err := client.Get(ctx, keys[0]).Result()
	if err != nil || stored != "hmac-digest" {
		t.Fatalf("stored code = %q, error = %v", stored, err)
	}
	if ttl := client.TTL(ctx, keys[0]).Val(); ttl <= 0 || ttl > 5*time.Minute {
		t.Fatalf("code TTL = %v, want (0, 5m]", ttl)
	}

	_, err = store.ReserveLoginCode(
		ctx, phone, ip, "other-digest", "reservation-2", bucket,
		5*time.Minute, time.Minute, time.Hour, time.Hour, 10, 30,
	)
	if !errors.Is(err, ErrSMSCooldown) {
		t.Fatalf("second ReserveLoginCode() error = %v, want ErrSMSCooldown", err)
	}
}

func TestVerifyLoginCodeWithRedis(t *testing.T) {
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

	store := NewSMSCodeStore(client, "familyos:test:verify")
	keysFor := func(phone string) []string {
		tag := "{" + phone + "}"
		return []string{store.prefix + ":sms:" + tag + ":code", store.prefix + ":sms:" + tag + ":failures"}
	}
	prepare := func(t *testing.T, phone, digest string) []string {
		t.Helper()
		keys := keysFor(phone)
		if err := client.Del(ctx, keys...).Err(); err != nil {
			t.Fatalf("cleanup test keys: %v", err)
		}
		if err := client.Set(ctx, keys[0], digest, 5*time.Minute).Err(); err != nil {
			t.Fatalf("store test code: %v", err)
		}
		t.Cleanup(func() { _ = client.Del(context.Background(), keys...).Err() })
		return keys
	}

	t.Run("success consumes code", func(t *testing.T) {
		phone, digest := "13800138001", "correct-digest"
		prepare(t, phone, digest)
		if err := store.VerifyLoginCode(ctx, phone, digest, 5); err != nil {
			t.Fatalf("VerifyLoginCode() error = %v", err)
		}
		if err := store.VerifyLoginCode(ctx, phone, digest, 5); !errors.Is(err, ErrSMSCodeInvalidOrExpired) {
			t.Fatalf("second VerifyLoginCode() error = %v, want invalid", err)
		}
	})

	t.Run("fifth failure locks code", func(t *testing.T) {
		phone := "13800138002"
		keys := prepare(t, phone, "correct-digest")
		for attempt := 1; attempt <= 4; attempt++ {
			if err := store.VerifyLoginCode(ctx, phone, "wrong-digest", 5); !errors.Is(err, ErrSMSCodeInvalidOrExpired) {
				t.Fatalf("attempt %d error = %v, want invalid", attempt, err)
			}
		}
		if err := store.VerifyLoginCode(ctx, phone, "wrong-digest", 5); !errors.Is(err, ErrSMSCodeAttemptsExceeded) {
			t.Fatalf("fifth attempt error = %v, want attempts exceeded", err)
		}
		if ttl := client.TTL(ctx, keys[1]).Val(); ttl <= 0 || ttl > 5*time.Minute {
			t.Fatalf("failures TTL = %v, want (0, 5m]", ttl)
		}
		if err := store.VerifyLoginCode(ctx, phone, "correct-digest", 5); !errors.Is(err, ErrSMSCodeAttemptsExceeded) {
			t.Fatalf("correct code after lock error = %v, want attempts exceeded", err)
		}
	})

	t.Run("concurrent requests consume once", func(t *testing.T) {
		phone, digest := "13800138003", "correct-digest"
		prepare(t, phone, digest)
		errs := make(chan error, 2)
		var wg sync.WaitGroup
		wg.Add(2)
		for range 2 {
			go func() {
				defer wg.Done()
				errs <- store.VerifyLoginCode(context.Background(), phone, digest, 5)
			}()
		}
		wg.Wait()
		close(errs)
		successes, invalid := 0, 0
		for err := range errs {
			switch {
			case err == nil:
				successes++
			case errors.Is(err, ErrSMSCodeInvalidOrExpired):
				invalid++
			default:
				t.Fatalf("unexpected concurrent error: %v", err)
			}
		}
		if successes != 1 || invalid != 1 {
			t.Fatalf("successes = %d, invalid = %d, want 1 and 1", successes, invalid)
		}
	})
}
