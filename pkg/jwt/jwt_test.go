package jwt

import (
	"strconv"
	"testing"
	"time"

	jwtlib "github.com/golang-jwt/jwt/v5"
)

func TestGenerateAndParseAccessTokenClaims(t *testing.T) {
	token, err := GenerateAccessToken("test-secret", "familyos", "familyos-mobile", 42, "13800138000", "session-id", "jwt-id", 15*time.Minute)
	if err != nil {
		t.Fatalf("GenerateAccessToken() error = %v", err)
	}
	claims, err := ParseAccessToken("test-secret", "familyos", "familyos-mobile", token)
	if err != nil {
		t.Fatalf("ParseAccessToken() error = %v", err)
	}
	if claims.Subject != strconv.FormatUint(42, 10) || claims.SessionID != "session-id" || claims.ID != "jwt-id" {
		t.Fatalf("unexpected claims: %+v", claims)
	}
	if claims.Issuer != "familyos" || len(claims.Audience) != 1 || claims.Audience[0] != "familyos-mobile" {
		t.Fatalf("unexpected issuer/audience: %+v", claims.RegisteredClaims)
	}
	if claims.IssuedAt == nil || claims.ExpiresAt == nil {
		t.Fatal("iat or exp is missing")
	}
	if ttl := claims.ExpiresAt.Sub(claims.IssuedAt.Time); ttl != 15*time.Minute {
		t.Fatalf("token TTL = %v, want 15m", ttl)
	}
}

func TestParseAccessTokenRequiresExpiration(t *testing.T) {
	claims := &Claims{
		UserID: 42, Phone: "13800138000", SessionID: "session-id",
		RegisteredClaims: jwtlib.RegisteredClaims{
			Subject: "42", ID: "jwt-id", Issuer: "familyos",
			Audience: jwtlib.ClaimStrings{"familyos-mobile"}, IssuedAt: jwtlib.NewNumericDate(time.Now()),
		},
	}
	token, err := jwtlib.NewWithClaims(jwtlib.SigningMethodHS256, claims).SignedString([]byte("test-secret"))
	if err != nil {
		t.Fatalf("SignedString() error = %v", err)
	}
	if _, err := ParseAccessToken("test-secret", "familyos", "familyos-mobile", token); err == nil {
		t.Fatal("ParseAccessToken() accepted a token without exp")
	}
}

func TestParseAccessTokenRejectsWrongIssuerOrAudience(t *testing.T) {
	token, err := GenerateAccessToken("test-secret", "familyos", "familyos-mobile", 42, "13800138000", "session-id", "jwt-id", 15*time.Minute)
	if err != nil {
		t.Fatalf("GenerateAccessToken() error = %v", err)
	}
	if _, err := ParseAccessToken("test-secret", "other", "familyos-mobile", token); err == nil {
		t.Fatal("ParseAccessToken() accepted wrong issuer")
	}
	if _, err := ParseAccessToken("test-secret", "familyos", "other", token); err == nil {
		t.Fatal("ParseAccessToken() accepted wrong audience")
	}
}
