package middleware

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	pkgjwt "github.com/lijunsheng/familyos/pkg/jwt"
)

const userIDContextKey = "auth_user_id"

func Auth(secret, issuer, audience string) gin.HandlerFunc {
	return func(c *gin.Context) {
		authorization := c.GetHeader("Authorization")
		parts := strings.SplitN(authorization, " ", 2)
		if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") || parts[1] == "" {
			abortUnauthorized(c)
			return
		}

		claims, err := pkgjwt.ParseAccessToken(secret, issuer, audience, parts[1])
		if err != nil {
			abortUnauthorized(c)
			return
		}
		userID, err := strconv.ParseUint(claims.Subject, 10, 64)
		if err != nil || userID == 0 || claims.UserID != userID || claims.SessionID == "" || claims.ID == "" {
			abortUnauthorized(c)
			return
		}
		c.Set(userIDContextKey, userID)
		c.Next()
	}
}

func CurrentUserID(c *gin.Context) uint64 {
	value, ok := c.Get(userIDContextKey)
	if !ok {
		return 0
	}
	userID, _ := value.(uint64)
	return userID
}

func abortUnauthorized(c *gin.Context) {
	c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
		"code":    1018,
		"message": "Access Token 无效或已过期",
	})
}
