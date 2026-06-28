package jwt

import (
	"errors"
	"time"

	jwtlib "github.com/golang-jwt/jwt/v5"
)

var (
	ErrTokenExpired = errors.New("token expired")
	ErrTokenInvalid = errors.New("token invalid")
)

// Claims 自定义 JWT 载荷
type Claims struct {
	UserID uint64 `json:"user_id"`
	Phone  string `json:"phone"`
	jwtlib.RegisteredClaims
}

// GenerateToken 生成 JWT Token，有效期 7 天
func GenerateToken(secret string, userID uint64, phone string) (string, error) {
	now := time.Now()
	claims := &Claims{
		UserID: userID,
		Phone:  phone,
		RegisteredClaims: jwtlib.RegisteredClaims{
			IssuedAt:  jwtlib.NewNumericDate(now),
			ExpiresAt: jwtlib.NewNumericDate(now.Add(7 * 24 * time.Hour)),
		},
	}

	token := jwtlib.NewWithClaims(jwtlib.SigningMethodHS256, claims)
	return token.SignedString([]byte(secret))
}

// ParseToken 解析 JWT Token
func ParseToken(secret, tokenStr string) (*Claims, error) {
	token, err := jwtlib.ParseWithClaims(tokenStr, &Claims{},
		func(t *jwtlib.Token) (any, error) {
			return []byte(secret), nil
		},
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
