package service

import (
	"context"
	"errors"
	"regexp"
	"testing"
	"time"
)

type fakeSMSStore struct {
	digest        string
	phone         string
	reservationID string
	retryAfter    time.Duration
	reserveErr    error
	rolledBack    bool
	verifyDigest  string
	verifyErr     error
}

func (f *fakeSMSStore) ReserveLoginCode(
	_ context.Context,
	phone, _ string,
	digest, reservationID, _ string,
	_, _, _, _ time.Duration,
	_, _ int64,
) (time.Duration, error) {
	f.phone = phone
	f.digest = digest
	f.reservationID = reservationID
	return f.retryAfter, f.reserveErr
}

func (f *fakeSMSStore) RollbackLoginCode(_ context.Context, _, _, reservationID, _ string) error {
	f.rolledBack = reservationID == f.reservationID
	return nil
}

func (f *fakeSMSStore) VerifyLoginCode(_ context.Context, phone, digest string, maxAttempts int64) error {
	f.phone = phone
	f.verifyDigest = digest
	if maxAttempts != maxSMSCodeAttempts {
		return errors.New("unexpected max attempts")
	}
	return f.verifyErr
}

type fakeSMSProvider struct {
	phone string
	code  string
	err   error
}

func (f *fakeSMSProvider) SendLoginCode(_ context.Context, phone, code string) error {
	f.phone = phone
	f.code = code
	return f.err
}

func newSMSService(store SMSCodeStore, sender SMSProvider) *AuthService {
	svc := &AuthService{}
	svc.ConfigureSMS(store, sender, SMSCodeConfig{
		HMACSecret:    "unit-test-secret",
		CodeTTL:       5 * time.Minute,
		Cooldown:      time.Minute,
		DailyLimit:    10,
		IPLimit:       30,
		IPLimitWindow: time.Hour,
	})
	return svc
}

func TestSendSMSCodeStoresDigestAndSendsSixDigits(t *testing.T) {
	store := &fakeSMSStore{retryAfter: time.Minute}
	sender := &fakeSMSProvider{}
	svc := newSMSService(store, sender)

	result, err := svc.SendSMSCode(context.Background(), "13800138000", "127.0.0.1")
	if err != nil {
		t.Fatalf("SendSMSCode() error = %v", err)
	}
	if result.RetryAfterSeconds != 60 {
		t.Fatalf("retry_after = %d, want 60", result.RetryAfterSeconds)
	}
	if !regexp.MustCompile(`^\d{6}$`).MatchString(sender.code) {
		t.Fatalf("code = %q, want six digits", sender.code)
	}
	if store.digest == sender.code || store.digest != digestSMSCode("unit-test-secret", sender.phone, sender.code) {
		t.Fatal("Redis store did not receive the expected HMAC digest")
	}
	if store.reservationID == "" {
		t.Fatal("reservation ID is empty")
	}
}

func TestSendSMSCodeRejectsInvalidPhoneBeforeRedis(t *testing.T) {
	store := &fakeSMSStore{}
	sender := &fakeSMSProvider{}
	_, err := newSMSService(store, sender).SendSMSCode(context.Background(), "123", "127.0.0.1")
	if !errors.Is(err, ErrInvalidPhone) {
		t.Fatalf("error = %v, want ErrInvalidPhone", err)
	}
	if store.phone != "" || sender.phone != "" {
		t.Fatal("invalid phone reached Redis or SMS provider")
	}
}

func TestSendSMSCodeReturnsCooldownWithoutSending(t *testing.T) {
	store := &fakeSMSStore{retryAfter: 42 * time.Second, reserveErr: ErrSMSCooldown}
	sender := &fakeSMSProvider{}
	result, err := newSMSService(store, sender).SendSMSCode(context.Background(), "13800138000", "127.0.0.1")
	if !errors.Is(err, ErrSMSCooldown) {
		t.Fatalf("error = %v, want ErrSMSCooldown", err)
	}
	if result == nil || result.RetryAfterSeconds != 42 {
		t.Fatalf("result = %+v, want retry_after 42", result)
	}
	if sender.phone != "" {
		t.Fatal("cooldown request reached SMS provider")
	}
}

func TestSendSMSCodeRollsBackWhenProviderFails(t *testing.T) {
	store := &fakeSMSStore{retryAfter: time.Minute}
	sender := &fakeSMSProvider{err: errors.New("provider unavailable")}
	_, err := newSMSService(store, sender).SendSMSCode(context.Background(), "13800138000", "127.0.0.1")
	if !errors.Is(err, ErrSMSSendFailed) {
		t.Fatalf("error = %v, want ErrSMSSendFailed", err)
	}
	if !store.rolledBack {
		t.Fatal("Redis reservation was not rolled back")
	}
}

func TestGenerateSMSCodeAlwaysReturnsSixDigits(t *testing.T) {
	for range 100 {
		code, err := generateSMSCode()
		if err != nil {
			t.Fatalf("generateSMSCode() error = %v", err)
		}
		if !regexp.MustCompile(`^\d{6}$`).MatchString(code) {
			t.Fatalf("code = %q, want six digits", code)
		}
	}
}

func TestVerifySMSCodePassesHMACDigestToStore(t *testing.T) {
	store := &fakeSMSStore{}
	svc := newSMSService(store, &fakeSMSProvider{})
	if err := svc.VerifySMSCode(context.Background(), "13800138000", "483921"); err != nil {
		t.Fatalf("VerifySMSCode() error = %v", err)
	}
	want := digestSMSCode("unit-test-secret", "13800138000", "483921")
	if store.verifyDigest != want {
		t.Fatalf("digest = %q, want %q", store.verifyDigest, want)
	}
}

func TestVerifySMSCodeMapsStoreFailureToUnavailable(t *testing.T) {
	store := &fakeSMSStore{verifyErr: errors.New("redis unavailable")}
	err := newSMSService(store, &fakeSMSProvider{}).VerifySMSCode(context.Background(), "13800138000", "483921")
	if !errors.Is(err, ErrSMSUnavailable) {
		t.Fatalf("error = %v, want ErrSMSUnavailable", err)
	}
}
