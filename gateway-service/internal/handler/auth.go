package handler

import (
	"context"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
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
	c.JSON(http.StatusOK, gin.H{
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
		"token":   resp.GetToken(),
		"user_id": resp.GetUserId(),
	})
}

// GetProfile GET /api/v1/auth/profile?user_id=1
func (h *AuthHandler) GetProfile(c *gin.Context) {
	userIDStr := c.DefaultQuery("user_id", "0")
	userID, err := strconv.ParseInt(userIDStr, 10, 64)
	if err != nil || userID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 user_id",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.GetProfile(ctx, &authv1.GetProfileRequest{UserId: userID})
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
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
		"token":   resp.GetToken(),
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
