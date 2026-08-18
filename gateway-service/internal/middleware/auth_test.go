package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	pkgjwt "github.com/lijunsheng/familyos/pkg/jwt"
)

func TestAuthMiddleware(t *testing.T) {
	gin.SetMode(gin.TestMode)
	const secret = "middleware-test-secret"
	validToken := accessTokenForTest(t, secret, "familyos", "familyos-mobile", 42, 15*time.Minute)
	tests := []struct {
		name          string
		authorization string
		wantStatus    int
	}{
		{name: "missing bearer", wantStatus: http.StatusUnauthorized},
		{name: "wrong scheme", authorization: "Basic " + validToken, wantStatus: http.StatusUnauthorized},
		{name: "wrong signature", authorization: "Bearer " + accessTokenForTest(t, "other-secret", "familyos", "familyos-mobile", 42, 15*time.Minute), wantStatus: http.StatusUnauthorized},
		{name: "wrong issuer", authorization: "Bearer " + accessTokenForTest(t, secret, "other", "familyos-mobile", 42, 15*time.Minute), wantStatus: http.StatusUnauthorized},
		{name: "wrong audience", authorization: "Bearer " + accessTokenForTest(t, secret, "familyos", "other", 42, 15*time.Minute), wantStatus: http.StatusUnauthorized},
		{name: "expired", authorization: "Bearer " + accessTokenForTest(t, secret, "familyos", "familyos-mobile", 42, -time.Minute), wantStatus: http.StatusUnauthorized},
		{name: "valid", authorization: "Bearer " + validToken, wantStatus: http.StatusOK},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			router := gin.New()
			router.Use(Auth(secret, "familyos", "familyos-mobile"))
			router.GET("/protected", func(c *gin.Context) {
				c.JSON(http.StatusOK, gin.H{"user_id": CurrentUserID(c)})
			})
			req := httptest.NewRequest(http.MethodGet, "/protected", nil)
			if tt.authorization != "" {
				req.Header.Set("Authorization", tt.authorization)
			}
			resp := httptest.NewRecorder()
			router.ServeHTTP(resp, req)
			if resp.Code != tt.wantStatus {
				t.Fatalf("status = %d, want %d; body=%s", resp.Code, tt.wantStatus, resp.Body.String())
			}
			if tt.wantStatus == http.StatusOK && resp.Body.String() != "{\"user_id\":42}" {
				t.Fatalf("body = %s, want authenticated user ID", resp.Body.String())
			}
		})
	}
}

func accessTokenForTest(t *testing.T, secret, issuer, audience string, userID uint64, ttl time.Duration) string {
	t.Helper()
	token, err := pkgjwt.GenerateAccessToken(secret, issuer, audience, userID, "13800138000", "session-id", "jwt-id", ttl)
	if err != nil {
		t.Fatalf("GenerateAccessToken() error = %v", err)
	}
	return token
}
