package service

import (
	"context"
	"testing"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
	pkgjwt "github.com/lijunsheng/familyos/pkg/jwt"
)

type fakeRefreshSessionStore struct {
	session    repository.RefreshSession
	secretHash string
	ttl        time.Duration
}

func (f *fakeRefreshSessionStore) Create(_ context.Context, session repository.RefreshSession, secretHash string, ttl time.Duration) error {
	f.session, f.secretHash, f.ttl = session, secretHash, ttl
	return nil
}

func (f *fakeRefreshSessionStore) Rotate(context.Context, string, string, string, time.Duration) (*repository.RefreshSession, error) {
	return nil, repository.ErrRefreshSessionNotFound
}

func (f *fakeRefreshSessionStore) Revoke(context.Context, uint64, string, string) error { return nil }
func (f *fakeRefreshSessionStore) Delete(context.Context, uint64, string) error         { return nil }
func (f *fakeRefreshSessionStore) UserID(context.Context, string) (uint64, error)       { return 0, nil }

func TestIssueTokenPairStoresOnlyRefreshSecretHash(t *testing.T) {
	store := &fakeRefreshSessionStore{}
	svc := &AuthService{jwtSecret: "test-jwt-secret"}
	svc.ConfigureTokens(store, TokenConfig{
		Issuer: "familyos", Audience: "familyos-mobile",
		AccessTTL: 15 * time.Minute, RefreshTTL: 30 * 24 * time.Hour,
	})
	user := &model.User{ID: 42, Phone: "13800138000", Status: model.UserStatusNormal}
	pair, err := svc.issueTokenPair(context.Background(), user, "test-device")
	if err != nil {
		t.Fatalf("issueTokenPair() error = %v", err)
	}
	sessionID, secret, err := parseRefreshToken(pair.RefreshToken)
	if err != nil {
		t.Fatalf("parseRefreshToken() error = %v", err)
	}
	if store.secretHash == secret || store.secretHash != hashRefreshSecret(secret) {
		t.Fatal("session store did not receive only the SHA-256 refresh secret hash")
	}
	if store.session.SessionID != sessionID || store.session.DeviceID != "test-device" || store.ttl != 30*24*time.Hour {
		t.Fatalf("unexpected stored session: %+v ttl=%v", store.session, store.ttl)
	}
	if pair.ExpiresIn != 900 {
		t.Fatalf("expires_in = %d, want 900", pair.ExpiresIn)
	}
	claims, err := pkgjwt.ParseAccessToken("test-jwt-secret", "familyos", "familyos-mobile", pair.AccessToken)
	if err != nil {
		t.Fatalf("ParseAccessToken() error = %v", err)
	}
	if claims.SessionID != sessionID || claims.Subject != "42" || claims.ID == "" {
		t.Fatalf("unexpected access claims: %+v", claims)
	}
}

func TestParseRefreshTokenRejectsMalformedValues(t *testing.T) {
	for _, token := range []string{"", "one-part", "a.b.c", "invalid.invalid"} {
		if _, _, err := parseRefreshToken(token); err == nil {
			t.Fatalf("parseRefreshToken(%q) accepted malformed token", token)
		}
	}
}
