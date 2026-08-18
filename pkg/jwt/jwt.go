package jwt

import (
	"errors"
	"strconv"
	"time"

	jwtlib "github.com/golang-jwt/jwt/v5"
)

var (
	ErrTokenExpired = errors.New("token expired")
	ErrTokenInvalid = errors.New("token invalid")
)

// Claims 自定义 JWT 载荷
type Claims struct {
	UserID    uint64 `json:"user_id"`
	Phone     string `json:"phone"`
	SessionID string `json:"sid"`
	jwtlib.RegisteredClaims
}

// GenerateAccessToken 生成短期 Access JWT。
func GenerateAccessToken(secret, issuer, audience string, userID uint64, phone, sessionID, tokenID string, ttl time.Duration) (string, error) {
	now := time.Now()
	claims := &Claims{
		UserID:    userID,
		Phone:     phone,
		SessionID: sessionID,
		RegisteredClaims: jwtlib.RegisteredClaims{
			Subject:   strconv.FormatUint(userID, 10),
			ID:        tokenID,
			Issuer:    issuer,
			Audience:  jwtlib.ClaimStrings{audience},
			IssuedAt:  jwtlib.NewNumericDate(now),
			ExpiresAt: jwtlib.NewNumericDate(now.Add(ttl)),
		},
	}

	token := jwtlib.NewWithClaims(jwtlib.SigningMethodHS256, claims)
	return token.SignedString([]byte(secret))
}

// ParseAccessToken 校验并解析 Access JWT。
func ParseAccessToken(secret, issuer, audience, tokenStr string) (*Claims, error) {
	token, err := jwtlib.ParseWithClaims(tokenStr, &Claims{},
		func(t *jwtlib.Token) (any, error) {
			return []byte(secret), nil
		},
		jwtlib.WithIssuer(issuer),
		jwtlib.WithAudience(audience),
		jwtlib.WithExpirationRequired(),
		jwtlib.WithValidMethods([]string{jwtlib.SigningMethodHS256.Alg()}),
	)
	if err != nil {
		if errors.Is(err, jwtlib.ErrTokenExpired) {
			return nil, ErrTokenExpired
		}
		return nil, ErrTokenInvalid
	}

	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid {
		return nil, ErrTokenInvalid
	}
	return claims, nil
}
