package handler

import (
	"context"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/lijunsheng/familyos/gateway-service/internal/middleware"
	authv1 "github.com/lijunsheng/familyos/proto/gen/auth/v1"
	"google.golang.org/grpc"
)

// AuthHandler 认证 HTTP 处理器
type AuthHandler struct {
	client authv1.AuthServiceClient
}

// NewAuthHandler 创建 AuthHandler
func NewAuthHandler(conn *grpc.ClientConn) *AuthHandler {
	return &AuthHandler{
		client: authv1.NewAuthServiceClient(conn),
	}
}

// SendSMSCode POST /api/v1/auth/sms/code
func (h *AuthHandler) SendSMSCode(c *gin.Context) {
	var body struct {
		Phone string `json:"phone"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请求格式错误"})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
	defer cancel()
	resp, err := h.client.SendSMSCode(ctx, &authv1.SendSMSCodeRequest{
		Phone:    body.Phone,
		ClientIp: c.ClientIP(),
	})
	if err != nil {
		log.Printf("gRPC SendSMSCode 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}

	status := http.StatusOK
	switch resp.GetCode() {
	case 1001:
		status = http.StatusBadRequest
	case 1007, 1008, 1009:
		status = http.StatusTooManyRequests
	case 1010, 1011:
		status = http.StatusServiceUnavailable
	case 0:
	default:
		status = http.StatusInternalServerError
	}
	c.JSON(status, gin.H{
		"code":                resp.GetCode(),
		"message":             resp.GetMessage(),
		"retry_after_seconds": resp.GetRetryAfterSeconds(),
	})
}

// SMSLogin POST /api/v1/auth/sms/login
func (h *AuthHandler) SMSLogin(c *gin.Context) {
	var body struct {
		Phone            string `json:"phone"`
		VerificationCode string `json:"verification_code"`
		DeviceID         string `json:"device_id"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请求格式错误"})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.SMSLogin(ctx, &authv1.SMSLoginRequest{
		Phone:            body.Phone,
		VerificationCode: body.VerificationCode,
		DeviceId:         body.DeviceID,
	})
	if err != nil {
		log.Printf("gRPC SMSLogin 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}

	status := http.StatusOK
	switch resp.GetCode() {
	case 1001, 1012:
		status = http.StatusBadRequest
	case 1006:
		status = http.StatusForbidden
	case 1013:
		status = http.StatusTooManyRequests
	case 1011, 1017:
		status = http.StatusServiceUnavailable
	case 0:
	default:
		status = http.StatusInternalServerError
	}

	user := resp.GetUser()
	var userBody any
	if user != nil {
		userBody = gin.H{
			"id": user.GetId(), "phone": user.GetPhone(), "nickname": user.GetNickname(),
			"avatar": user.GetAvatar(), "gender": user.GetGender(), "status": user.GetStatus(),
			"last_login_at": user.GetLastLoginAt(), "created_at": user.GetCreatedAt(), "updated_at": user.GetUpdatedAt(),
		}
	}
	c.JSON(status, gin.H{
		"code": resp.GetCode(), "message": resp.GetMessage(),
		"access_token": resp.GetAccessToken(), "refresh_token": resp.GetRefreshToken(),
		"expires_in": resp.GetExpiresIn(), "is_new_user": resp.GetIsNewUser(), "user": userBody,
	})
}

// RefreshToken POST /api/v1/auth/refresh
func (h *AuthHandler) RefreshToken(c *gin.Context) {
	refreshToken, ok := bindRefreshToken(c)
	if !ok {
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.RefreshToken(ctx, &authv1.RefreshTokenRequest{RefreshToken: refreshToken})
	if err != nil {
		log.Printf("gRPC RefreshToken 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	status := tokenSessionHTTPStatus(resp.GetCode())
	c.JSON(status, gin.H{
		"code": resp.GetCode(), "message": resp.GetMessage(),
		"access_token": resp.GetAccessToken(), "refresh_token": resp.GetRefreshToken(), "expires_in": resp.GetExpiresIn(),
	})
}

// Logout POST /api/v1/auth/logout
func (h *AuthHandler) Logout(c *gin.Context) {
	refreshToken, ok := bindRefreshToken(c)
	if !ok {
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.Logout(ctx, &authv1.LogoutRequest{RefreshToken: refreshToken})
	if err != nil {
		log.Printf("gRPC Logout 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	c.JSON(tokenSessionHTTPStatus(resp.GetCode()), gin.H{"code": resp.GetCode(), "message": resp.GetMessage()})
}

func bindRefreshToken(c *gin.Context) (string, bool) {
	authorization := c.GetHeader("Authorization")
	if parts := strings.SplitN(authorization, " ", 2); len(parts) == 2 && strings.EqualFold(parts[0], "Bearer") && parts[1] != "" {
		return parts[1], true
	}
	var body struct {
		RefreshToken string `json:"refresh_token"`
	}
	if err := c.ShouldBindJSON(&body); err != nil || body.RefreshToken == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1015, "message": "Refresh Token 无效或已过期"})
		return "", false
	}
	return body.RefreshToken, true
}

func tokenSessionHTTPStatus(code int32) int {
	switch code {
	case 0:
		return http.StatusOK
	case 1006:
		return http.StatusForbidden
	case 1015, 1016:
		return http.StatusUnauthorized
	case 1017:
		return http.StatusServiceUnavailable
	default:
		return http.StatusInternalServerError
	}
}

// Register POST /api/v1/auth/register
func (h *AuthHandler) Register(c *gin.Context) {
	var req authv1.RegisterRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.Register(ctx, &req)
	if err != nil {
		log.Printf("gRPC Register 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	// 不能直接序列化 proto struct — omitempty 会让 code:0 被丢弃
	user := resp.GetUser()
	c.JSON(http.StatusOK, gin.H{
		"code":          resp.GetCode(),
		"message":       resp.GetMessage(),
		"user_id":       resp.GetUserId(),
		"access_token":  resp.GetAccessToken(),
		"refresh_token": resp.GetRefreshToken(),
		"expires_in":    resp.GetExpiresIn(),
		"user": gin.H{
			"id": user.GetId(), "phone": user.GetPhone(), "nickname": user.GetNickname(),
			"avatar": user.GetAvatar(), "gender": user.GetGender(), "status": user.GetStatus(),
			"last_login_at": user.GetLastLoginAt(), "created_at": user.GetCreatedAt(), "updated_at": user.GetUpdatedAt(),
		},
	})
}

// GetProfile GET /api/v1/auth/profile
func (h *AuthHandler) GetProfile(c *gin.Context) {
	userID := middleware.CurrentUserID(c)

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.GetProfile(ctx, &authv1.GetProfileRequest{UserId: int64(userID)})
	if err != nil {
		log.Printf("gRPC GetProfile 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	user := resp.GetUser()
	c.JSON(http.StatusOK, gin.H{
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
		"user": gin.H{
			"id":            user.GetId(),
			"phone":         user.GetPhone(),
			"nickname":      user.GetNickname(),
			"avatar":        user.GetAvatar(),
			"gender":        user.GetGender(),
			"status":        user.GetStatus(),
			"last_login_at": user.GetLastLoginAt(),
			"created_at":    user.GetCreatedAt(),
			"updated_at":    user.GetUpdatedAt(),
		},
		"family_name": resp.GetFamilyName(),
	})
}

// UpdateProfile PUT /api/v1/auth/profile
func (h *AuthHandler) UpdateProfile(c *gin.Context) {
	var req authv1.UpdateProfileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}
	req.UserId = int64(middleware.CurrentUserID(c))

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.UpdateProfile(ctx, &req)
	if err != nil {
		log.Printf("gRPC UpdateProfile 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
	})
}

// Login POST /api/v1/auth/login
func (h *AuthHandler) Login(c *gin.Context) {
	var req authv1.LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.Login(ctx, &req)
	if err != nil {
		log.Printf("gRPC Login 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	user := resp.GetUser()
	c.JSON(http.StatusOK, gin.H{
		"code":          resp.GetCode(),
		"message":       resp.GetMessage(),
		"access_token":  resp.GetAccessToken(),
		"refresh_token": resp.GetRefreshToken(),
		"expires_in":    resp.GetExpiresIn(),
		"user": gin.H{
			"id":            user.GetId(),
			"phone":         user.GetPhone(),
			"nickname":      user.GetNickname(),
			"avatar":        user.GetAvatar(),
			"gender":        user.GetGender(),
			"status":        user.GetStatus(),
			"last_login_at": user.GetLastLoginAt(),
			"created_at":    user.GetCreatedAt(),
			"updated_at":    user.GetUpdatedAt(),
		},
	})
}
