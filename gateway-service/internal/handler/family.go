package handler

import (
	"context"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	familyv1 "github.com/lijunsheng/familyos/proto/gen/family/v1"
	"google.golang.org/grpc"
)

// FamilyHandler 家庭 HTTP 处理器
type FamilyHandler struct {
	client familyv1.FamilyServiceClient
}

// NewFamilyHandler 创建 FamilyHandler
func NewFamilyHandler(conn *grpc.ClientConn) *FamilyHandler {
	return &FamilyHandler{
		client: familyv1.NewFamilyServiceClient(conn),
	}
}

// GetMyFamily GET /api/v1/family/my?user_id=1
func (h *FamilyHandler) GetMyFamily(c *gin.Context) {
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

	resp, err := h.client.GetMyFamily(ctx, &familyv1.GetMyFamilyRequest{UserId: userID})
	if err != nil {
		log.Printf("gRPC GetMyFamily 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	f := resp.GetFamily()
	if f == nil {
		c.JSON(http.StatusOK, gin.H{
			"code":    resp.GetCode(),
			"message": resp.GetMessage(),
			"family":  nil,
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
		"family": gin.H{
			"id":               f.GetId(),
			"name":             f.GetName(),
			"avatar":           f.GetAvatar(),
			"description":      f.GetDescription(),
			"owner_user_id":    f.GetOwnerUserId(),
			"invite_code":      f.GetInviteCode(),
			"member_count":     f.GetMemberCount(),
			"max_member_count": f.GetMaxMemberCount(),
			"my_role":          f.GetMyRole(),
			"created_at":       f.GetCreatedAt(),
			"updated_at":       f.GetUpdatedAt(),
		},
	})
}

// CreateFamily POST /api/v1/family/create
func (h *FamilyHandler) CreateFamily(c *gin.Context) {
	var req familyv1.CreateFamilyRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.CreateFamily(ctx, &req)
	if err != nil {
		log.Printf("gRPC CreateFamily 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":        resp.GetCode(),
		"message":     resp.GetMessage(),
		"family_id":   resp.GetFamilyId(),
		"invite_code": resp.GetInviteCode(),
	})
}

// UpdateFamily PUT /api/v1/family/{family_id}
func (h *FamilyHandler) UpdateFamily(c *gin.Context) {
	familyIDStr := c.Param("family_id")
	familyID, err := strconv.ParseInt(familyIDStr, 10, 64)
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 family_id",
		})
		return
	}

	var body struct {
		UserID      int64  `json:"user_id"`
		Name        string `json:"name"`
		Avatar      string `json:"avatar"`
		Description string `json:"description"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	req := &familyv1.UpdateFamilyRequest{
		FamilyId:    familyID,
		UserId:      body.UserID,
		Name:        body.Name,
		Avatar:      body.Avatar,
		Description: body.Description,
	}

	resp, err := h.client.UpdateFamily(ctx, req)
	if err != nil {
		log.Printf("gRPC UpdateFamily 调用失败: %v", err)
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

// JoinFamily POST /api/v1/family/join
func (h *FamilyHandler) JoinFamily(c *gin.Context) {
	var req familyv1.JoinFamilyRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.JoinFamily(ctx, &req)
	if err != nil {
		log.Printf("gRPC JoinFamily 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":      resp.GetCode(),
		"message":   resp.GetMessage(),
		"family_id": resp.GetFamilyId(),
	})
}

// LeaveFamily POST /api/v1/family/leave
func (h *FamilyHandler) LeaveFamily(c *gin.Context) {
	var req familyv1.LeaveFamilyRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.LeaveFamily(ctx, &req)
	if err != nil {
		log.Printf("gRPC LeaveFamily 调用失败: %v", err)
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

// DissolveFamily DELETE /api/v1/family/{family_id}
func (h *FamilyHandler) DissolveFamily(c *gin.Context) {
	familyIDStr := c.Param("family_id")
	familyID, err := strconv.ParseInt(familyIDStr, 10, 64)
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 family_id",
		})
		return
	}

	var body struct {
		UserID int64 `json:"user_id"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	req := &familyv1.DissolveFamilyRequest{
		FamilyId: familyID,
		UserId:   body.UserID,
	}

	resp, err := h.client.DissolveFamily(ctx, req)
	if err != nil {
		log.Printf("gRPC DissolveFamily 调用失败: %v", err)
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

// ListMembers GET /api/v1/family/{family_id}/members?user_id=1
func (h *FamilyHandler) ListMembers(c *gin.Context) {
	familyIDStr := c.Param("family_id")
	familyID, err := strconv.ParseInt(familyIDStr, 10, 64)
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 family_id",
		})
		return
	}

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

	resp, err := h.client.ListMembers(ctx, &familyv1.ListMembersRequest{
		FamilyId: familyID,
		UserId:   userID,
	})
	if err != nil {
		log.Printf("gRPC ListMembers 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	members := make([]gin.H, 0, len(resp.GetMembers()))
	for _, m := range resp.GetMembers() {
		members = append(members, gin.H{
			"user_id":      m.GetUserId(),
			"phone":        m.GetPhone(),
			"nickname":     m.GetNickname(),
			"avatar":       m.GetAvatar(),
			"role":         m.GetRole(),
			"relation":     m.GetRelation(),
			"display_name": m.GetDisplayName(),
			"joined_at":    m.GetJoinedAt(),
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
		"members": members,
	})
}

// UpdateMember PUT /api/v1/family/{family_id}/members/{member_user_id}
func (h *FamilyHandler) UpdateMember(c *gin.Context) {
	familyIDStr := c.Param("family_id")
	familyID, err := strconv.ParseInt(familyIDStr, 10, 64)
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 family_id",
		})
		return
	}

	memberIDStr := c.Param("member_user_id")
	memberID, err := strconv.ParseInt(memberIDStr, 10, 64)
	if err != nil || memberID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 member_user_id",
		})
		return
	}

	var body struct {
		OperatorUserID int64  `json:"operator_user_id"`
		Role           int32  `json:"role"`
		Relation       string `json:"relation"`
		DisplayName    string `json:"display_name"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	req := &familyv1.UpdateMemberRequest{
		FamilyId:       familyID,
		OperatorUserId: body.OperatorUserID,
		MemberUserId:   memberID,
		Role:           body.Role,
		Relation:       body.Relation,
		DisplayName:    body.DisplayName,
	}

	resp, err := h.client.UpdateMember(ctx, req)
	if err != nil {
		log.Printf("gRPC UpdateMember 调用失败: %v", err)
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

// RemoveMember DELETE /api/v1/family/{family_id}/members/{member_user_id}
func (h *FamilyHandler) RemoveMember(c *gin.Context) {
	familyIDStr := c.Param("family_id")
	familyID, err := strconv.ParseInt(familyIDStr, 10, 64)
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 family_id",
		})
		return
	}

	memberIDStr := c.Param("member_user_id")
	memberID, err := strconv.ParseInt(memberIDStr, 10, 64)
	if err != nil || memberID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 member_user_id",
		})
		return
	}

	var body struct {
		OperatorUserID int64 `json:"operator_user_id"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	req := &familyv1.RemoveMemberRequest{
		FamilyId:       familyID,
		OperatorUserId: body.OperatorUserID,
		MemberUserId:   memberID,
	}

	resp, err := h.client.RemoveMember(ctx, req)
	if err != nil {
		log.Printf("gRPC RemoveMember 调用失败: %v", err)
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

// ResetInviteCode POST /api/v1/family/{family_id}/invite-code/reset
func (h *FamilyHandler) ResetInviteCode(c *gin.Context) {
	familyIDStr := c.Param("family_id")
	familyID, err := strconv.ParseInt(familyIDStr, 10, 64)
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 family_id",
		})
		return
	}

	var body struct {
		UserID      int64 `json:"user_id"`
		ExpireHours int32 `json:"expire_hours"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	req := &familyv1.ResetInviteCodeRequest{
		FamilyId:    familyID,
		UserId:      body.UserID,
		ExpireHours: body.ExpireHours,
	}

	resp, err := h.client.ResetInviteCode(ctx, req)
	if err != nil {
		log.Printf("gRPC ResetInviteCode 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":                    resp.GetCode(),
		"message":                 resp.GetMessage(),
		"invite_code":             resp.GetInviteCode(),
		"invite_code_expired_at":  resp.GetInviteCodeExpiredAt(),
	})
}
