package handler

import (
	"context"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/lijunsheng/familyos/gateway-service/internal/middleware"
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

// GetMyFamily GET /api/v1/family/my
func (h *FamilyHandler) GetMyFamily(c *gin.Context) {
	userID := int64(middleware.CurrentUserID(c))

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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
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

// GetDietaryProfile GET /api/v1/family/{family_id}/dietary-profile。
func (h *FamilyHandler) GetDietaryProfile(c *gin.Context) {
	familyID, err := strconv.ParseInt(c.Param("family_id"), 10, 64)
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请提供有效的 family_id"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.GetDietaryProfile(ctx, &familyv1.GetDietaryProfileRequest{FamilyId: familyID, UserId: int64(middleware.CurrentUserID(c))})
	if err != nil {
		log.Printf("gRPC GetDietaryProfile 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "profile": familyDietaryProfileJSON(resp.GetProfile())})
}

// SaveDietaryProfile PUT /api/v1/family/{family_id}/dietary-profile。
func (h *FamilyHandler) SaveDietaryProfile(c *gin.Context) {
	familyID, err := strconv.ParseInt(c.Param("family_id"), 10, 64)
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请提供有效的 family_id"})
		return
	}
	var body struct {
		BudgetMin      *float64 `json:"budget_min"`
		BudgetMax      *float64 `json:"budget_max"`
		BudgetCurrency string   `json:"budget_currency"`
		BudgetPeriod   int32    `json:"budget_period"`
		Notes          string   `json:"notes"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请求格式错误"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	req := &familyv1.SaveDietaryProfileRequest{FamilyId: familyID, UserId: int64(middleware.CurrentUserID(c)), BudgetCurrency: body.BudgetCurrency, BudgetPeriod: body.BudgetPeriod, Notes: body.Notes}
	if body.BudgetMin != nil {
		req.BudgetMin = body.BudgetMin
	}
	if body.BudgetMax != nil {
		req.BudgetMax = body.BudgetMax
	}
	resp, err := h.client.SaveDietaryProfile(ctx, req)
	if err != nil {
		log.Printf("gRPC SaveDietaryProfile 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "profile": familyDietaryProfileJSON(resp.GetProfile())})
}

// familyDietaryProfileJSON 将家庭饮食档案转换为 HTTP JSON。
func familyDietaryProfileJSON(profile *familyv1.FamilyDietaryProfileInfo) gin.H {
	if profile == nil {
		return nil
	}
	result := gin.H{"id": profile.GetId(), "family_id": profile.GetFamilyId(), "budget_currency": profile.GetBudgetCurrency(), "budget_period": profile.GetBudgetPeriod(), "notes": profile.GetNotes(), "updated_by": profile.GetUpdatedBy(), "created_at": profile.GetCreatedAt(), "updated_at": profile.GetUpdatedAt()}
	if profile.BudgetMin != nil {
		result["budget_min"] = profile.GetBudgetMin()
	}
	if profile.BudgetMax != nil {
		result["budget_max"] = profile.GetBudgetMax()
	}
	return result
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
	req.UserId = int64(middleware.CurrentUserID(c))

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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
		"code":        resp.GetCode(),
		"message":     resp.GetMessage(),
		"family_id":   resp.GetFamilyId(),
		"invite_code": resp.GetInviteCode(),
	})
}

// CreateMealPlan POST /api/v1/family/meal-plans
func (h *FamilyHandler) CreateMealPlan(c *gin.Context) {
	var body struct {
		FamilyID   int64  `json:"family_id"`
		DishID     int64  `json:"dish_id"`
		MealDate   string `json:"meal_date"`
		MealType   int32  `json:"meal_type"`
		Servings   int32  `json:"servings"`
		CookUserID *int64 `json:"cook_user_id"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请求格式错误",
		})
		return
	}
	if body.FamilyID <= 0 || body.DishID <= 0 ||
		(body.CookUserID != nil && *body.CookUserID <= 0) {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "family_id、dish_id 和 cook_user_id 必须是有效ID",
		})
		return
	}

	req := &familyv1.CreateMealPlanRequest{
		FamilyId:  body.FamilyID,
		DishId:    body.DishID,
		MealDate:  body.MealDate,
		MealType:  body.MealType,
		Servings:  body.Servings,
		CreatedBy: int64(middleware.CurrentUserID(c)),
	}
	if body.CookUserID != nil {
		req.CookUserId = body.CookUserID
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.CreateMealPlan(ctx, req)
	if err != nil {
		log.Printf("gRPC CreateMealPlan 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}
	if resp.GetCode() != 0 || resp.GetMealPlan() == nil {
		c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
			"code":    resp.GetCode(),
			"message": resp.GetMessage(),
		})
		return
	}

	plan := resp.GetMealPlan()
	var cookUserID any
	if plan.CookUserId != nil {
		cookUserID = plan.GetCookUserId()
	}
	c.JSON(http.StatusCreated, gin.H{
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
		"meal_plan": gin.H{
			"id":           plan.GetId(),
			"family_id":    plan.GetFamilyId(),
			"dish_id":      plan.GetDishId(),
			"meal_date":    plan.GetMealDate(),
			"meal_type":    plan.GetMealType(),
			"servings":     plan.GetServings(),
			"cook_user_id": cookUserID,
			"status":       plan.GetStatus(),
			"created_by":   plan.GetCreatedBy(),
			"created_at":   plan.GetCreatedAt(),
			"updated_at":   plan.GetUpdatedAt(),
		},
	})
}

// ListMealPlans GET /api/v1/family/{family_id}/meal-plans
func (h *FamilyHandler) ListMealPlans(c *gin.Context) {
	familyID, err := strconv.ParseInt(c.Param("family_id"), 10, 64)
	userID := int64(middleware.CurrentUserID(c))
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请提供有效的 family_id"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.ListMealPlans(ctx, &familyv1.ListMealPlansRequest{
		FamilyId: familyID, UserId: userID, StartDate: c.Query("start_date"), EndDate: c.Query("end_date"),
	})
	if err != nil {
		log.Printf("gRPC ListMealPlans 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	if resp.GetCode() != 0 {
		c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{"code": resp.GetCode(), "message": resp.GetMessage()})
		return
	}
	plans := make([]gin.H, 0, len(resp.GetMealPlans()))
	for _, plan := range resp.GetMealPlans() {
		plans = append(plans, mealPlanJSON(plan))
	}
	c.JSON(http.StatusOK, gin.H{"code": 0, "message": resp.GetMessage(), "meal_plans": plans})
}

// UpdateMealPlan PATCH /api/v1/family/meal-plans/{id}
func (h *FamilyHandler) UpdateMealPlan(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请提供有效的菜单记录ID"})
		return
	}
	var body struct {
		MealDate   *string `json:"meal_date"`
		MealType   *int32  `json:"meal_type"`
		Servings   *int32  `json:"servings"`
		CookUserID *int64  `json:"cook_user_id"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请求格式错误"})
		return
	}
	req := &familyv1.UpdateMealPlanRequest{Id: id, UserId: int64(middleware.CurrentUserID(c)), MealDate: body.MealDate, MealType: body.MealType, Servings: body.Servings, CookUserId: body.CookUserID}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.UpdateMealPlan(ctx, req)
	if err != nil {
		log.Printf("gRPC UpdateMealPlan 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	if resp.GetCode() != 0 || resp.GetMealPlan() == nil {
		c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{"code": resp.GetCode(), "message": resp.GetMessage()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"code": 0, "message": resp.GetMessage(), "meal_plan": mealPlanJSON(resp.GetMealPlan())})
}

// DeleteMealPlan DELETE /api/v1/family/meal-plans/{id}
func (h *FamilyHandler) DeleteMealPlan(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请提供有效的菜单记录ID"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.DeleteMealPlan(ctx, &familyv1.DeleteMealPlanRequest{Id: id, UserId: int64(middleware.CurrentUserID(c))})
	if err != nil {
		log.Printf("gRPC DeleteMealPlan 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{"code": resp.GetCode(), "message": resp.GetMessage()})
}

// familyHTTPStatus 将家庭模块业务码映射为 HTTP 状态码，保持客户端可直接判断失败类型。
func familyHTTPStatus(code int32) int {
	switch code {
	case 0:
		return http.StatusOK
	case 1004, 2001, 2009, 2104, 2107, 2201, 2202:
		return http.StatusNotFound
	case 2002, 2006:
		return http.StatusConflict
	case 2003, 2004, 2007:
		return http.StatusForbidden
	case 1999:
		return http.StatusInternalServerError
	default:
		return http.StatusBadRequest
	}
}

// mealPlanJSON 将菜单 Proto 对象转换为稳定的 HTTP JSON 响应结构。
func mealPlanJSON(plan *familyv1.FamilyMealPlanInfo) gin.H {
	var cookUserID any
	if plan.CookUserId != nil {
		cookUserID = plan.GetCookUserId()
	}
	return gin.H{
		"id": plan.GetId(), "family_id": plan.GetFamilyId(), "dish_id": plan.GetDishId(),
		"dish_name": plan.GetDishName(), "dish_image_key": plan.GetDishImageKey(),
		"meal_date": plan.GetMealDate(), "meal_type": plan.GetMealType(), "servings": plan.GetServings(),
		"cook_user_id": cookUserID, "cook_user_name": plan.GetCookUserName(), "status": plan.GetStatus(),
		"created_by": plan.GetCreatedBy(), "created_at": plan.GetCreatedAt(), "updated_at": plan.GetUpdatedAt(),
	}
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
		UserId:      int64(middleware.CurrentUserID(c)),
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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
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
	req.UserId = int64(middleware.CurrentUserID(c))

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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
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
	req.UserId = int64(middleware.CurrentUserID(c))

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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
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

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	req := &familyv1.DissolveFamilyRequest{
		FamilyId: familyID,
		UserId:   int64(middleware.CurrentUserID(c)),
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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
	})
}

// ListMembers GET /api/v1/family/{family_id}/members
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

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.ListMembers(ctx, &familyv1.ListMembersRequest{
		FamilyId: familyID,
		UserId:   int64(middleware.CurrentUserID(c)),
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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
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
		Role        int32  `json:"role"`
		Relation    string `json:"relation"`
		DisplayName string `json:"display_name"`
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
		OperatorUserId: int64(middleware.CurrentUserID(c)),
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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
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

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	req := &familyv1.RemoveMemberRequest{
		FamilyId:       familyID,
		OperatorUserId: int64(middleware.CurrentUserID(c)),
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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
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
		UserId:      int64(middleware.CurrentUserID(c)),
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

	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{
		"code":                   resp.GetCode(),
		"message":                resp.GetMessage(),
		"invite_code":            resp.GetInviteCode(),
		"invite_code_expired_at": resp.GetInviteCodeExpiredAt(),
	})
}
