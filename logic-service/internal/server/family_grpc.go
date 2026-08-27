package server

import (
	"context"
	"errors"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/service"
	familyv1 "github.com/lijunsheng/familyos/proto/gen/family/v1"
)

// 家庭模块状态码
const (
	// 成功
	FamilyCodeSuccess = 0

	// 家庭业务错误（对齐文档 2001-2009）
	FamilyCodeNotFound              = 2001
	FamilyCodeAlreadyIn             = 2002
	FamilyCodeNotIn                 = 2003
	FamilyCodeNoPermission          = 2004
	FamilyCodeInvalidCode           = 2005
	FamilyCodeFull                  = 2006
	FamilyCodeCannotOpOwner         = 2007
	FamilyCodeInvalidName           = 2008
	FamilyCodeMemberNotFound        = 2009
	FamilyCodeInvalidDietaryProfile = 2010

	MealPlanCodeInvalidDate     = 2101
	MealPlanCodeInvalidType     = 2102
	MealPlanCodeInvalidServings = 2103
	MealPlanCodeDishNotFound    = 2104
	MealPlanCodeCookNotInFamily = 2105
	MealPlanCodeInvalidIDs      = 2106
	MealPlanCodeNotFound        = 2107
	MealPlanCodeInvalidRange    = 2108
	MealPlanCodeInvalidStatus   = 2109
	MealPlanCodeCookOnlyStatus  = 2110
	MealPlanCodeNotCompleted    = 2111
	MealPlanCodeInvalidRating   = 2112

	ShoppingCodeListNotFound = 2201
	ShoppingCodeItemNotFound = 2202
	ShoppingCodeInvalidDate  = 2203
	ShoppingCodeInvalidName  = 2204
	ShoppingCodeInvalidItem  = 2205
)

// FamilyServer gRPC FamilyService 实现
type FamilyServer struct {
	familyv1.UnimplementedFamilyServiceServer
	svc         *service.FamilyService
	mealPlanSvc *service.MealPlanService
	shoppingSvc *service.ShoppingListService
}

// NewFamilyServer 创建 FamilyServer
func NewFamilyServer(svc *service.FamilyService, mealPlanSvc *service.MealPlanService, shoppingSvc *service.ShoppingListService) *FamilyServer {
	return &FamilyServer{svc: svc, mealPlanSvc: mealPlanSvc, shoppingSvc: shoppingSvc}
}

// ─── GetMyFamily ─────────────────────────────────────────────

func (s *FamilyServer) GetMyFamily(ctx context.Context, req *familyv1.GetMyFamilyRequest) (*familyv1.GetMyFamilyResponse, error) {
	result, err := s.svc.GetMyFamily(ctx, uint64(req.UserId))
	if err != nil {
		return &familyv1.GetMyFamilyResponse{
			Code:    CodeInternalError,
			Message: err.Error(),
		}, nil
	}

	if result.Family == nil {
		return &familyv1.GetMyFamilyResponse{
			Code:    FamilyCodeSuccess,
			Message: "暂未加入家庭",
			Family:  nil,
		}, nil
	}

	return &familyv1.GetMyFamilyResponse{
		Code:    FamilyCodeSuccess,
		Message: "查询成功",
		Family:  toFamilyInfo(result.Family, result.MyRole),
	}, nil
}

// ─── CreateFamily ────────────────────────────────────────────

func (s *FamilyServer) CreateFamily(ctx context.Context, req *familyv1.CreateFamilyRequest) (*familyv1.CreateFamilyResponse, error) {
	var avatar, description *string
	if req.Avatar != "" {
		avatar = &req.Avatar
	}
	if req.Description != "" {
		description = &req.Description
	}

	result, err := s.svc.CreateFamily(ctx, uint64(req.UserId), req.Name, avatar, description)
	if err != nil {
		return &familyv1.CreateFamilyResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CreateFamilyResponse{
		Code:       FamilyCodeSuccess,
		Message:    "创建成功",
		FamilyId:   int64(result.FamilyID),
		InviteCode: result.InviteCode,
	}, nil
}

// ─── UpdateFamily ────────────────────────────────────────────

func (s *FamilyServer) UpdateFamily(ctx context.Context, req *familyv1.UpdateFamilyRequest) (*familyv1.CommonResponse, error) {
	// name: 为空不修改（不允许清空家庭名称）
	var name *string
	if req.Name != "" {
		name = &req.Name
	}
	// avatar / description: 始终传指针（空字符串表示清空）
	avatar := &req.Avatar
	description := &req.Description

	err := s.svc.UpdateFamily(ctx, uint64(req.UserId), uint64(req.FamilyId), name, avatar, description)
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "更新成功",
	}, nil
}

// ─── JoinFamily ──────────────────────────────────────────────

func (s *FamilyServer) JoinFamily(ctx context.Context, req *familyv1.JoinFamilyRequest) (*familyv1.JoinFamilyResponse, error) {
	var relation, displayName *string
	if req.Relation != "" {
		relation = &req.Relation
	}
	if req.DisplayName != "" {
		displayName = &req.DisplayName
	}

	result, err := s.svc.JoinFamily(ctx, uint64(req.UserId), req.InviteCode, relation, displayName)
	if err != nil {
		return &familyv1.JoinFamilyResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.JoinFamilyResponse{
		Code:     FamilyCodeSuccess,
		Message:  "加入成功",
		FamilyId: int64(result.FamilyID),
	}, nil
}

// ─── LeaveFamily ─────────────────────────────────────────────

func (s *FamilyServer) LeaveFamily(ctx context.Context, req *familyv1.LeaveFamilyRequest) (*familyv1.CommonResponse, error) {
	err := s.svc.LeaveFamily(ctx, uint64(req.UserId))
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "退出成功",
	}, nil
}

// ─── DissolveFamily ──────────────────────────────────────────

func (s *FamilyServer) DissolveFamily(ctx context.Context, req *familyv1.DissolveFamilyRequest) (*familyv1.CommonResponse, error) {
	err := s.svc.DissolveFamily(ctx, uint64(req.UserId), uint64(req.FamilyId))
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "解散成功",
	}, nil
}

// ─── ListMembers ─────────────────────────────────────────────

func (s *FamilyServer) ListMembers(ctx context.Context, req *familyv1.ListMembersRequest) (*familyv1.ListMembersResponse, error) {
	members, err := s.svc.ListMembers(ctx, uint64(req.UserId), uint64(req.FamilyId))
	if err != nil {
		return &familyv1.ListMembersResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	infos := make([]*familyv1.FamilyMemberInfo, 0, len(members))
	for _, m := range members {
		infos = append(infos, toFamilyMemberInfo(&m))
	}

	return &familyv1.ListMembersResponse{
		Code:    FamilyCodeSuccess,
		Message: "查询成功",
		Members: infos,
	}, nil
}

// GetDietaryProfile 查询家庭饮食档案。
func (s *FamilyServer) GetDietaryProfile(ctx context.Context, req *familyv1.GetDietaryProfileRequest) (*familyv1.GetDietaryProfileResponse, error) {
	profile, err := s.svc.GetDietaryProfile(ctx, uint64(req.GetUserId()), uint64(req.GetFamilyId()))
	if err != nil {
		return &familyv1.GetDietaryProfileResponse{Code: mapFamilyErrorCode(err), Message: err.Error()}, nil
	}
	response := &familyv1.GetDietaryProfileResponse{Code: FamilyCodeSuccess, Message: "查询成功"}
	if profile != nil {
		response.Profile = toFamilyDietaryProfileInfo(profile)
	}
	return response, nil
}

// SaveDietaryProfile 保存家庭饮食档案。
func (s *FamilyServer) SaveDietaryProfile(ctx context.Context, req *familyv1.SaveDietaryProfileRequest) (*familyv1.SaveDietaryProfileResponse, error) {
	profile := model.FamilyDietaryProfile{BudgetPeriod: int8(req.GetBudgetPeriod()), BudgetCurrency: req.GetBudgetCurrency(), Notes: req.GetNotes()}
	if req.BudgetMin != nil {
		value := req.GetBudgetMin()
		profile.BudgetMin = &value
	}
	if req.BudgetMax != nil {
		value := req.GetBudgetMax()
		profile.BudgetMax = &value
	}
	saved, err := s.svc.SaveDietaryProfile(ctx, uint64(req.GetUserId()), uint64(req.GetFamilyId()), profile)
	if err != nil {
		return &familyv1.SaveDietaryProfileResponse{Code: mapFamilyErrorCode(err), Message: err.Error()}, nil
	}
	return &familyv1.SaveDietaryProfileResponse{Code: FamilyCodeSuccess, Message: "保存成功", Profile: toFamilyDietaryProfileInfo(saved)}, nil
}

// ─── UpdateMember ────────────────────────────────────────────

func (s *FamilyServer) UpdateMember(ctx context.Context, req *familyv1.UpdateMemberRequest) (*familyv1.CommonResponse, error) {
	// role: 0 = 不修改，>0 = 修改为新角色
	var role *int32
	if req.Role > 0 {
		role = &req.Role
	}
	// relation / display_name: 始终传指针（空字符串表示清空字段）
	relation := &req.Relation
	displayName := &req.DisplayName

	err := s.svc.UpdateMember(ctx,
		uint64(req.OperatorUserId),
		uint64(req.FamilyId),
		uint64(req.MemberUserId),
		role, relation, displayName,
	)
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "更新成功",
	}, nil
}

// ─── RemoveMember ────────────────────────────────────────────

func (s *FamilyServer) RemoveMember(ctx context.Context, req *familyv1.RemoveMemberRequest) (*familyv1.CommonResponse, error) {
	err := s.svc.RemoveMember(ctx,
		uint64(req.OperatorUserId),
		uint64(req.FamilyId),
		uint64(req.MemberUserId),
	)
	if err != nil {
		return &familyv1.CommonResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CommonResponse{
		Code:    FamilyCodeSuccess,
		Message: "移除成功",
	}, nil
}

// ─── ResetInviteCode ─────────────────────────────────────────

func (s *FamilyServer) ResetInviteCode(ctx context.Context, req *familyv1.ResetInviteCodeRequest) (*familyv1.ResetInviteCodeResponse, error) {
	var expireHours *int32
	if req.ExpireHours > 0 {
		expireHours = &req.ExpireHours
	}

	result, err := s.svc.ResetInviteCode(ctx, uint64(req.UserId), uint64(req.FamilyId), expireHours)
	if err != nil {
		return &familyv1.ResetInviteCodeResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	expiredAtStr := ""
	if result.InviteCodeExpiredAt != nil {
		expiredAtStr = result.InviteCodeExpiredAt.Format("2006-01-02 15:04:05")
	}

	return &familyv1.ResetInviteCodeResponse{
		Code:                FamilyCodeSuccess,
		Message:             "重置成功",
		InviteCode:          result.InviteCode,
		InviteCodeExpiredAt: expiredAtStr,
	}, nil
}

// ─── CreateMealPlan ──────────────────────────────────────────

func (s *FamilyServer) CreateMealPlan(ctx context.Context, req *familyv1.CreateMealPlanRequest) (*familyv1.CreateMealPlanResponse, error) {
	if req.GetFamilyId() <= 0 || req.GetDishId() <= 0 || req.GetCreatedBy() <= 0 ||
		(req.CookUserId != nil && req.GetCookUserId() <= 0) {
		return &familyv1.CreateMealPlanResponse{
			Code:    MealPlanCodeInvalidIDs,
			Message: service.ErrInvalidMealPlanIDs.Error(),
		}, nil
	}

	var cookUserID *uint64
	if req.CookUserId != nil {
		value := uint64(req.GetCookUserId())
		cookUserID = &value
	}

	plan, err := s.mealPlanSvc.CreateMealPlan(
		ctx,
		uint64(req.GetFamilyId()),
		uint64(req.GetDishId()),
		req.GetMealDate(),
		req.GetMealType(),
		int(req.GetServings()),
		cookUserID,
		uint64(req.GetCreatedBy()),
	)
	if err != nil {
		return &familyv1.CreateMealPlanResponse{
			Code:    mapFamilyErrorCode(err),
			Message: err.Error(),
		}, nil
	}

	return &familyv1.CreateMealPlanResponse{
		Code:     FamilyCodeSuccess,
		Message:  "已加入家庭菜单",
		MealPlan: toFamilyMealPlanInfo(plan),
	}, nil
}

func (s *FamilyServer) ListMealPlans(ctx context.Context, req *familyv1.ListMealPlansRequest) (*familyv1.ListMealPlansResponse, error) {
	plans, err := s.mealPlanSvc.ListMealPlans(ctx, uint64(req.GetFamilyId()), uint64(req.GetUserId()), req.GetStartDate(), req.GetEndDate())
	if err != nil {
		return &familyv1.ListMealPlansResponse{Code: mapFamilyErrorCode(err), Message: err.Error()}, nil
	}
	infos := make([]*familyv1.FamilyMealPlanInfo, 0, len(plans))
	for i := range plans {
		info := toFamilyMealPlanInfo(&plans[i].FamilyMealPlan)
		info.DishName = plans[i].DishName
		info.DishImageKey = plans[i].DishImageKey
		info.CookUserName = plans[i].CookUserName
		infos = append(infos, info)
	}
	return &familyv1.ListMealPlansResponse{Code: FamilyCodeSuccess, Message: "查询成功", MealPlans: infos}, nil
}

func (s *FamilyServer) UpdateMealPlan(ctx context.Context, req *familyv1.UpdateMealPlanRequest) (*familyv1.CreateMealPlanResponse, error) {
	var servings *int
	if req.Servings != nil {
		value := int(req.GetServings())
		servings = &value
	}
	var cookUserID *uint64
	if req.CookUserId != nil {
		value := uint64(req.GetCookUserId())
		cookUserID = &value
	}
	plan, err := s.mealPlanSvc.UpdateMealPlan(ctx, uint64(req.GetId()), uint64(req.GetUserId()), req.MealDate, req.MealType, servings, cookUserID, req.Status)
	if err != nil {
		return &familyv1.CreateMealPlanResponse{Code: mapFamilyErrorCode(err), Message: err.Error()}, nil
	}
	return &familyv1.CreateMealPlanResponse{Code: FamilyCodeSuccess, Message: "修改成功", MealPlan: toFamilyMealPlanInfo(plan)}, nil
}

// UpsertMealPlanRating 保存或更新当前用户对已完成家庭菜单的评价。
func (s *FamilyServer) UpsertMealPlanRating(ctx context.Context, req *familyv1.UpsertMealPlanRatingRequest) (*familyv1.MealPlanRatingResponse, error) {
	value, err := s.mealPlanSvc.UpsertRating(ctx, uint64(req.GetMealPlanId()), uint64(req.GetUserId()), req.GetRating(), req.GetComment())
	if err != nil {
		return &familyv1.MealPlanRatingResponse{Code: mapFamilyErrorCode(err), Message: err.Error()}, nil
	}
	return &familyv1.MealPlanRatingResponse{Code: FamilyCodeSuccess, Message: "评价已保存", Rating: toMealPlanRatingInfo(value)}, nil
}

// ListMealPlanRatings 查询某次家庭菜单的成员评价。
func (s *FamilyServer) ListMealPlanRatings(ctx context.Context, req *familyv1.ListMealPlanRatingsRequest) (*familyv1.MealPlanRatingsResponse, error) {
	values, average, count, myRating, myComment, err := s.mealPlanSvc.ListRatings(ctx, uint64(req.GetMealPlanId()), uint64(req.GetUserId()))
	if err != nil {
		return &familyv1.MealPlanRatingsResponse{Code: mapFamilyErrorCode(err), Message: err.Error()}, nil
	}
	result := make([]*familyv1.MealPlanRatingInfo, 0, len(values))
	for i := range values {
		result = append(result, toMealPlanRatingViewInfo(&values[i]))
	}
	response := &familyv1.MealPlanRatingsResponse{Code: FamilyCodeSuccess, Message: "查询成功", Ratings: result, AverageRating: average, RatingCount: int32(count), MyComment: myComment}
	if myRating != nil {
		value := int32(*myRating)
		response.MyRating = &value
	}
	return response, nil
}

func (s *FamilyServer) DeleteMealPlan(ctx context.Context, req *familyv1.DeleteMealPlanRequest) (*familyv1.CommonResponse, error) {
	if err := s.mealPlanSvc.DeleteMealPlan(ctx, uint64(req.GetId()), uint64(req.GetUserId())); err != nil {
		return &familyv1.CommonResponse{Code: mapFamilyErrorCode(err), Message: err.Error()}, nil
	}
	return &familyv1.CommonResponse{Code: FamilyCodeSuccess, Message: "删除成功"}, nil
}

// GenerateShoppingList 根据家庭菜单汇总食材并创建购物清单。
func (s *FamilyServer) GenerateShoppingList(ctx context.Context, req *familyv1.GenerateShoppingListRequest) (*familyv1.ShoppingListResponse, error) {
	result, err := s.shoppingSvc.GenerateShoppingList(ctx, uint64(req.GetUserId()), uint64(req.GetFamilyId()), req.GetStartDate(), req.GetEndDate(), req.GetName())
	if err != nil {
		return &familyv1.ShoppingListResponse{Code: mapShoppingErrorCode(err), Message: err.Error()}, nil
	}
	return shoppingListResponse(result, "购物清单生成成功"), nil
}

// ListShoppingLists 查询当前家庭的购物清单。
func (s *FamilyServer) ListShoppingLists(ctx context.Context, req *familyv1.ListShoppingListsRequest) (*familyv1.ShoppingListsResponse, error) {
	lists, err := s.shoppingSvc.ListShoppingLists(ctx, uint64(req.GetUserId()), uint64(req.GetFamilyId()))
	if err != nil {
		return &familyv1.ShoppingListsResponse{Code: mapShoppingErrorCode(err), Message: err.Error()}, nil
	}
	items := make([]*familyv1.ShoppingListInfo, 0, len(lists))
	for index := range lists {
		items = append(items, toShoppingListInfo(&lists[index]))
	}
	return &familyv1.ShoppingListsResponse{Code: FamilyCodeSuccess, Message: "查询成功", ShoppingLists: items}, nil
}

// GetShoppingList 查询购物清单及项目。
func (s *FamilyServer) GetShoppingList(ctx context.Context, req *familyv1.GetShoppingListRequest) (*familyv1.ShoppingListResponse, error) {
	result, err := s.shoppingSvc.GetShoppingList(ctx, uint64(req.GetUserId()), uint64(req.GetId()))
	if err != nil {
		return &familyv1.ShoppingListResponse{Code: mapShoppingErrorCode(err), Message: err.Error()}, nil
	}
	return shoppingListResponse(result, "查询成功"), nil
}

// UpdateShoppingItemPurchased 更新购物项目的购买状态。
func (s *FamilyServer) UpdateShoppingItemPurchased(ctx context.Context, req *familyv1.UpdateShoppingItemPurchasedRequest) (*familyv1.CommonResponse, error) {
	purchasedQuantity := 0.0
	purchased := req.GetIsPurchased()
	if req.PurchasedQuantity != nil {
		purchasedQuantity = req.GetPurchasedQuantity()
		purchased = purchasedQuantity > 0
	}
	err := s.shoppingSvc.UpdateItemPurchased(ctx, uint64(req.GetUserId()), uint64(req.GetItemId()), purchasedQuantity, purchased)
	if err != nil {
		return &familyv1.CommonResponse{Code: mapShoppingErrorCode(err), Message: err.Error()}, nil
	}
	return &familyv1.CommonResponse{Code: FamilyCodeSuccess, Message: "更新成功"}, nil
}

// AddManualShoppingItem 添加手动购物项目。
func (s *FamilyServer) AddManualShoppingItem(ctx context.Context, req *familyv1.AddManualShoppingItemRequest) (*familyv1.ShoppingItemResponse, error) {
	var quantity *float64
	if req.Quantity != nil {
		value := req.GetQuantity()
		quantity = &value
	}
	item, err := s.shoppingSvc.AddManualItem(ctx, uint64(req.GetUserId()), uint64(req.GetShoppingListId()), req.GetIngredientName(), quantity, req.GetQuantityText(), req.GetUnit())
	if err != nil {
		return &familyv1.ShoppingItemResponse{Code: mapShoppingErrorCode(err), Message: err.Error()}, nil
	}
	return &familyv1.ShoppingItemResponse{Code: FamilyCodeSuccess, Message: "添加成功", Item: toShoppingItemInfo(item)}, nil
}

// DeleteShoppingItem 删除购物项目。
func (s *FamilyServer) DeleteShoppingItem(ctx context.Context, req *familyv1.DeleteShoppingItemRequest) (*familyv1.CommonResponse, error) {
	if err := s.shoppingSvc.DeleteItem(ctx, uint64(req.GetUserId()), uint64(req.GetItemId())); err != nil {
		return &familyv1.CommonResponse{Code: mapShoppingErrorCode(err), Message: err.Error()}, nil
	}
	return &familyv1.CommonResponse{Code: FamilyCodeSuccess, Message: "删除成功"}, nil
}

// ─── 错误码映射 ──────────────────────────────────────────────

func mapFamilyErrorCode(err error) int32 {
	switch {
	case errors.Is(err, service.ErrFamilyNotFound):
		return FamilyCodeNotFound
	case errors.Is(err, service.ErrUserAlreadyInFamily):
		return FamilyCodeAlreadyIn
	case errors.Is(err, service.ErrUserNotInFamily):
		return FamilyCodeNotIn
	case errors.Is(err, service.ErrInvalidDietaryProfile):
		return FamilyCodeInvalidDietaryProfile
	case errors.Is(err, service.ErrNoFamilyPermission):
		return FamilyCodeNoPermission
	case errors.Is(err, service.ErrInvalidInviteCode):
		return FamilyCodeInvalidCode
	case errors.Is(err, service.ErrFamilyFull):
		return FamilyCodeFull
	case errors.Is(err, service.ErrCannotOperateOwner):
		return FamilyCodeCannotOpOwner
	case errors.Is(err, service.ErrInvalidFamilyName):
		return FamilyCodeInvalidName
	case errors.Is(err, service.ErrMemberNotFound):
		return FamilyCodeMemberNotFound
	case errors.Is(err, service.ErrInvalidMealPlanIDs):
		return MealPlanCodeInvalidIDs
	case errors.Is(err, service.ErrInvalidMealDate):
		return MealPlanCodeInvalidDate
	case errors.Is(err, service.ErrInvalidMealType):
		return MealPlanCodeInvalidType
	case errors.Is(err, service.ErrInvalidMealServings):
		return MealPlanCodeInvalidServings
	case errors.Is(err, service.ErrMealPlanDishNotFound):
		return MealPlanCodeDishNotFound
	case errors.Is(err, service.ErrCookUserNotInFamily):
		return MealPlanCodeCookNotInFamily
	case errors.Is(err, service.ErrMealPlanNotFound):
		return MealPlanCodeNotFound
	case errors.Is(err, service.ErrInvalidMealDateRange):
		return MealPlanCodeInvalidRange
	case errors.Is(err, service.ErrInvalidMealPlanStatus):
		return MealPlanCodeInvalidStatus
	case errors.Is(err, service.ErrCookOnlyCanUpdateStatus):
		return MealPlanCodeCookOnlyStatus
	case errors.Is(err, service.ErrMealPlanNotCompleted):
		return MealPlanCodeNotCompleted
	case errors.Is(err, service.ErrInvalidMealPlanRating):
		return MealPlanCodeInvalidRating
	case errors.Is(err, service.ErrUserNotFound):
		return CodeUserNotFound
	default:
		return CodeInternalError
	}
}

// toMealPlanRatingInfo 将评价模型转换为 Proto 响应。
func toMealPlanRatingInfo(value *model.FamilyMealPlanRating) *familyv1.MealPlanRatingInfo {
	return &familyv1.MealPlanRatingInfo{Id: int64(value.ID), MealPlanId: int64(value.MealPlanID), UserId: int64(value.UserID), Rating: int32(value.Rating), Comment: value.Comment, CreatedAt: value.CreatedAt.Format("2006-01-02 15:04:05"), UpdatedAt: value.UpdatedAt.Format("2006-01-02 15:04:05")}
}

// toMealPlanRatingViewInfo 将带用户昵称的评价模型转换为 Proto 响应。
func toMealPlanRatingViewInfo(value *model.FamilyMealPlanRatingView) *familyv1.MealPlanRatingInfo {
	result := toMealPlanRatingInfo(&value.FamilyMealPlanRating)
	result.UserName = value.UserName
	return result
}

// toFamilyDietaryProfileInfo 将家庭饮食档案转换为 Proto 响应。
func toFamilyDietaryProfileInfo(profile *model.FamilyDietaryProfile) *familyv1.FamilyDietaryProfileInfo {
	info := &familyv1.FamilyDietaryProfileInfo{Id: int64(profile.ID), FamilyId: int64(profile.FamilyID), BudgetCurrency: profile.BudgetCurrency, BudgetPeriod: int32(profile.BudgetPeriod), Notes: profile.Notes, UpdatedBy: int64(profile.UpdatedBy), CreatedAt: profile.CreatedAt.Format("2006-01-02 15:04:05"), UpdatedAt: profile.UpdatedAt.Format("2006-01-02 15:04:05")}
	if profile.BudgetMin != nil {
		value := *profile.BudgetMin
		info.BudgetMin = &value
	}
	if profile.BudgetMax != nil {
		value := *profile.BudgetMax
		info.BudgetMax = &value
	}
	return info
}

// mapShoppingErrorCode 将购物清单错误转换为对外业务码。
func mapShoppingErrorCode(err error) int32 {
	switch {
	case errors.Is(err, service.ErrShoppingListNotFound):
		return ShoppingCodeListNotFound
	case errors.Is(err, service.ErrShoppingItemNotFound):
		return ShoppingCodeItemNotFound
	case errors.Is(err, service.ErrInvalidShoppingDate):
		return ShoppingCodeInvalidDate
	case errors.Is(err, service.ErrInvalidShoppingName):
		return ShoppingCodeInvalidName
	case errors.Is(err, service.ErrInvalidShoppingItem):
		return ShoppingCodeInvalidItem
	case errors.Is(err, service.ErrUserNotInFamily):
		return FamilyCodeNotIn
	default:
		return CodeInternalError
	}
}

// shoppingListResponse 将购物清单领域对象转换为 gRPC 响应。
func shoppingListResponse(result *service.ShoppingListResult, message string) *familyv1.ShoppingListResponse {
	items := make([]*familyv1.ShoppingItemInfo, 0, len(result.Items))
	for index := range result.Items {
		items = append(items, toShoppingItemInfo(&result.Items[index]))
	}
	return &familyv1.ShoppingListResponse{Code: FamilyCodeSuccess, Message: message, ShoppingList: toShoppingListInfo(result.List), Items: items}
}

// toShoppingListInfo 将购物清单模型转换为 Proto 信息。
func toShoppingListInfo(list *model.ShoppingList) *familyv1.ShoppingListInfo {
	return &familyv1.ShoppingListInfo{Id: int64(list.ID), FamilyId: int64(list.FamilyID), CreatedBy: int64(list.CreatedBy), Name: list.Name, StartDate: list.StartDate.Format("2006-01-02"), EndDate: list.EndDate.Format("2006-01-02"), Status: int32(list.Status), CreatedAt: list.CreatedAt.Format("2006-01-02 15:04:05"), UpdatedAt: list.UpdatedAt.Format("2006-01-02 15:04:05")}
}

// toShoppingItemInfo 将购物项目模型转换为 Proto 信息。
func toShoppingItemInfo(item *model.ShoppingListItem) *familyv1.ShoppingItemInfo {
	info := &familyv1.ShoppingItemInfo{Id: int64(item.ID), ShoppingListId: int64(item.ShoppingListID), IngredientName: item.IngredientName, QuantityText: item.QuantityText, Unit: item.Unit, IsPurchased: item.IsPurchased == model.ShoppingItemPurchased, PurchasedQuantity: item.PurchasedQuantity, Source: item.Source, SortOrder: int32(item.SortOrder), CreatedAt: item.CreatedAt.Format("2006-01-02 15:04:05"), UpdatedAt: item.UpdatedAt.Format("2006-01-02 15:04:05")}
	if item.Quantity != nil {
		value := *item.Quantity
		info.Quantity = &value
	}
	return info
}

// ─── Proto 转换 ──────────────────────────────────────────────

func toFamilyInfo(f *model.Family, myRole int8) *familyv1.FamilyInfo {
	info := &familyv1.FamilyInfo{
		Id:             int64(f.ID),
		Name:           f.Name,
		OwnerUserId:    int64(f.OwnerUserID),
		InviteCode:     f.InviteCode,
		MemberCount:    int32(f.MemberCount),
		MaxMemberCount: int32(f.MaxMemberCount),
		MyRole:         int32(myRole),
		CreatedAt:      f.CreatedAt.Format("2006-01-02 15:04:05"),
		UpdatedAt:      f.UpdatedAt.Format("2006-01-02 15:04:05"),
	}
	if f.Avatar != nil {
		info.Avatar = *f.Avatar
	}
	if f.Description != nil {
		info.Description = *f.Description
	}
	return info
}

func toFamilyMemberInfo(m *model.FamilyMemberWithUser) *familyv1.FamilyMemberInfo {
	info := &familyv1.FamilyMemberInfo{
		UserId:   int64(m.UserID),
		Phone:    m.Phone,
		Nickname: m.Nickname,
		Role:     int32(m.Role),
		JoinedAt: m.JoinedAt.Format("2006-01-02 15:04:05"),
	}
	if m.Avatar != nil {
		info.Avatar = *m.Avatar
	}
	if m.Relation != nil {
		info.Relation = *m.Relation
	}
	if m.DisplayName != nil {
		info.DisplayName = *m.DisplayName
	}
	return info
}

func toFamilyMealPlanInfo(plan *model.FamilyMealPlan) *familyv1.FamilyMealPlanInfo {
	info := &familyv1.FamilyMealPlanInfo{
		Id:        int64(plan.ID),
		FamilyId:  int64(plan.FamilyID),
		DishId:    int64(plan.DishID),
		MealDate:  plan.MealDate.Format("2006-01-02"),
		MealType:  int32(plan.MealType),
		Servings:  int32(plan.Servings),
		Status:    int32(plan.Status),
		CreatedBy: int64(plan.CreatedBy),
		CreatedAt: plan.CreatedAt.Format("2006-01-02 15:04:05"),
		UpdatedAt: plan.UpdatedAt.Format("2006-01-02 15:04:05"),
	}
	if plan.CookUserID != nil {
		cookUserID := int64(*plan.CookUserID)
		info.CookUserId = &cookUserID
	}
	return info
}
