package service

import (
	"context"
	"errors"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
)

var (
	ErrInvalidMealPlanIDs      = errors.New("家庭、菜谱、创建人和负责人ID必须有效")
	ErrInvalidMealDate         = errors.New("用餐日期格式不正确")
	ErrInvalidMealType         = errors.New("餐次类型不正确")
	ErrInvalidMealServings     = errors.New("用餐人数必须在1到20之间")
	ErrMealPlanDishNotFound    = errors.New("菜谱不存在或已下架")
	ErrCookUserNotInFamily     = errors.New("做饭负责人不是该家庭成员")
	ErrMealPlanNotFound        = errors.New("家庭菜单记录不存在")
	ErrInvalidMealDateRange    = errors.New("日期范围不正确")
	ErrInvalidMealPlanStatus   = errors.New("做菜状态不正确")
	ErrCookOnlyCanUpdateStatus = errors.New("只有指定做菜人可以修改做菜状态")
	ErrMealPlanNotCompleted    = errors.New("菜谱完成后才可以评价")
	ErrInvalidMealPlanRating   = errors.New("评分必须在1到5分之间")
)

// MealPlanService 家庭菜单计划业务逻辑。
type MealPlanService struct {
	mealPlanRepo *repository.MealPlanRepo
	familyRepo   *repository.FamilyRepo
	dishRepo     *repository.DishRepo
	ratingRepo   *repository.FamilyMealPlanRatingRepo
}

func (s *MealPlanService) ListMealPlans(ctx context.Context, familyID, userID uint64, startDateText, endDateText string) ([]model.FamilyMealPlanView, error) {
	if familyID == 0 || userID == 0 {
		return nil, ErrInvalidMealPlanIDs
	}
	if err := s.requireFamilyMember(ctx, familyID, userID); err != nil {
		return nil, err
	}
	startDate, err := parseMealDate(startDateText)
	if err != nil {
		return nil, err
	}
	endDate, err := parseMealDate(endDateText)
	if err != nil {
		return nil, err
	}
	if endDate.Before(startDate) || endDate.Sub(startDate) > 31*24*time.Hour {
		return nil, ErrInvalidMealDateRange
	}
	return s.mealPlanRepo.ListWithDetails(ctx, familyID, startDate, endDate)
}

func (s *MealPlanService) UpdateMealPlan(ctx context.Context, id, userID uint64, mealDateText *string, mealType *int32, servings *int, cookUserID *uint64, status *int32) (*model.FamilyMealPlan, error) {
	if id == 0 || userID == 0 {
		return nil, ErrInvalidMealPlanIDs
	}
	plan, err := s.mealPlanRepo.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}
	if plan == nil {
		return nil, ErrMealPlanNotFound
	}
	if err := s.requireFamilyMember(ctx, plan.FamilyID, userID); err != nil {
		return nil, err
	}
	// 状态权限必须基于更新前的负责人，禁止通过同一个请求先给自己分配任务再越权改状态。
	if status != nil {
		if cookUserID != nil {
			return nil, ErrInvalidMealPlanStatus
		}
		if plan.CookUserID == nil || *plan.CookUserID != userID {
			return nil, ErrCookOnlyCanUpdateStatus
		}
		if *status < int32(model.MealPlanStatusPending) || *status > int32(model.MealPlanStatusCancelled) || !validMealPlanTransition(plan.Status, int8(*status)) {
			return nil, ErrInvalidMealPlanStatus
		}
	}
	values := make(map[string]any)
	if mealDateText != nil {
		mealDate, err := parseMealDate(*mealDateText)
		if err != nil {
			return nil, err
		}
		values["meal_date"] = mealDate
		plan.MealDate = mealDate
	}
	if mealType != nil {
		if *mealType < int32(model.MealTypeBreakfast) || *mealType > int32(model.MealTypeDinner) {
			return nil, ErrInvalidMealType
		}
		values["meal_type"] = int8(*mealType)
		plan.MealType = int8(*mealType)
	}
	if servings != nil {
		if *servings < 1 || *servings > 20 {
			return nil, ErrInvalidMealServings
		}
		values["servings"] = *servings
		plan.Servings = *servings
	}
	if cookUserID != nil {
		if *cookUserID == 0 {
			values["cook_user_id"] = nil
			plan.CookUserID = nil
		} else {
			cook, err := s.familyRepo.GetMember(ctx, plan.FamilyID, *cookUserID)
			if err != nil {
				return nil, err
			}
			if cook == nil {
				return nil, ErrCookUserNotInFamily
			}
			values["cook_user_id"] = *cookUserID
			plan.CookUserID = cookUserID
		}
	}
	if status != nil {
		values["status"] = int8(*status)
		plan.Status = int8(*status)
	}
	if len(values) > 0 {
		if err := s.mealPlanRepo.Update(ctx, id, values); err != nil {
			return nil, err
		}
		plan.UpdatedAt = time.Now()
	}
	return plan, nil
}

// ConfigureRatingRepo 注入评价仓储，保持菜单服务的依赖边界清晰。
func (s *MealPlanService) ConfigureRatingRepo(ratingRepo *repository.FamilyMealPlanRatingRepo) {
	s.ratingRepo = ratingRepo
}

// UpsertRating 保存当前家庭成员对已完成菜单的评分。
func (s *MealPlanService) UpsertRating(ctx context.Context, mealPlanID, userID uint64, rating int32, comment string) (*model.FamilyMealPlanRating, error) {
	if mealPlanID == 0 || userID == 0 {
		return nil, ErrInvalidMealPlanIDs
	}
	if rating < 1 || rating > 5 {
		return nil, ErrInvalidMealPlanRating
	}
	if s.ratingRepo == nil {
		return nil, errors.New("评价服务未配置")
	}
	plan, err := s.mealPlanRepo.GetByID(ctx, mealPlanID)
	if err != nil {
		return nil, err
	}
	if plan == nil {
		return nil, ErrMealPlanNotFound
	}
	if err := s.requireFamilyMember(ctx, plan.FamilyID, userID); err != nil {
		return nil, err
	}
	if plan.Status != model.MealPlanStatusCompleted {
		return nil, ErrMealPlanNotCompleted
	}
	value, err := s.ratingRepo.GetByMealPlanUser(ctx, mealPlanID, userID)
	if err != nil {
		return nil, err
	}
	if value == nil {
		value = &model.FamilyMealPlanRating{MealPlanID: mealPlanID, UserID: userID}
	}
	value.Rating = int8(rating)
	value.Comment = comment
	if err := s.ratingRepo.Save(ctx, value); err != nil {
		return nil, err
	}
	return value, nil
}

// ListRatings 查询某次已完成菜单的评价并返回当前用户评价。
func (s *MealPlanService) ListRatings(ctx context.Context, mealPlanID, userID uint64) ([]model.FamilyMealPlanRatingView, float64, int, *int8, string, error) {
	if mealPlanID == 0 || userID == 0 {
		return nil, 0, 0, nil, "", ErrInvalidMealPlanIDs
	}
	if s.ratingRepo == nil {
		return nil, 0, 0, nil, "", errors.New("评价服务未配置")
	}
	plan, err := s.mealPlanRepo.GetByID(ctx, mealPlanID)
	if err != nil {
		return nil, 0, 0, nil, "", err
	}
	if plan == nil {
		return nil, 0, 0, nil, "", ErrMealPlanNotFound
	}
	if err := s.requireFamilyMember(ctx, plan.FamilyID, userID); err != nil {
		return nil, 0, 0, nil, "", err
	}
	values, err := s.ratingRepo.ListByMealPlan(ctx, mealPlanID)
	if err != nil {
		return nil, 0, 0, nil, "", err
	}
	var total int
	var myRating *int8
	var myComment string
	for i := range values {
		total += int(values[i].Rating)
		if values[i].UserID == userID {
			value := values[i].Rating
			myRating = &value
			myComment = values[i].Comment
		}
	}
	var average float64
	if len(values) > 0 {
		average = float64(total) / float64(len(values))
	}
	return values, average, len(values), myRating, myComment, nil
}

// validMealPlanTransition 限制做菜状态只能按业务流程向前流转。
func validMealPlanTransition(current, next int8) bool {
	if current == next {
		return true
	}
	return (current == model.MealPlanStatusPending && (next == model.MealPlanStatusCooking || next == model.MealPlanStatusCancelled)) ||
		(current == model.MealPlanStatusCooking && next == model.MealPlanStatusCompleted)
}

func (s *MealPlanService) DeleteMealPlan(ctx context.Context, id, userID uint64) error {
	if id == 0 || userID == 0 {
		return ErrInvalidMealPlanIDs
	}
	plan, err := s.mealPlanRepo.GetByID(ctx, id)
	if err != nil {
		return err
	}
	if plan == nil {
		return ErrMealPlanNotFound
	}
	if err := s.requireFamilyMember(ctx, plan.FamilyID, userID); err != nil {
		return err
	}
	return s.mealPlanRepo.Delete(ctx, id)
}

func (s *MealPlanService) requireFamilyMember(ctx context.Context, familyID, userID uint64) error {
	member, err := s.familyRepo.GetMember(ctx, familyID, userID)
	if err != nil {
		return err
	}
	if member == nil {
		return ErrNoFamilyPermission
	}
	return nil
}

func parseMealDate(value string) (time.Time, error) {
	// MySQL DSN 未指定 loc 时，go-sql-driver/mysql 使用 UTC。
	// meal_date 是不含时区的 DATE，统一按 UTC 解析可避免本地零点转 UTC 后落到前一天。
	date, err := time.Parse("2006-01-02", value)
	if err != nil {
		return time.Time{}, ErrInvalidMealDate
	}
	return date, nil
}

func NewMealPlanService(
	mealPlanRepo *repository.MealPlanRepo,
	familyRepo *repository.FamilyRepo,
	dishRepo *repository.DishRepo,
) *MealPlanService {
	return &MealPlanService{
		mealPlanRepo: mealPlanRepo,
		familyRepo:   familyRepo,
		dishRepo:     dishRepo,
	}
}

// CreateMealPlan 将菜谱加入家庭菜单。
func (s *MealPlanService) CreateMealPlan(
	ctx context.Context,
	familyID, dishID uint64,
	mealDateText string,
	mealType int32,
	servings int,
	cookUserID *uint64,
	createdBy uint64,
) (*model.FamilyMealPlan, error) {
	if familyID == 0 || dishID == 0 || createdBy == 0 || (cookUserID != nil && *cookUserID == 0) {
		return nil, ErrInvalidMealPlanIDs
	}
	mealDate, err := parseMealDate(mealDateText)
	if err != nil {
		return nil, err
	}
	if mealType < int32(model.MealTypeBreakfast) || mealType > int32(model.MealTypeDinner) {
		return nil, ErrInvalidMealType
	}
	if servings < 1 || servings > 20 {
		return nil, ErrInvalidMealServings
	}

	creator, err := s.familyRepo.GetMember(ctx, familyID, createdBy)
	if err != nil {
		return nil, err
	}
	if creator == nil {
		return nil, ErrNoFamilyPermission
	}

	family, err := s.familyRepo.GetFamilyByID(ctx, familyID)
	if err != nil {
		return nil, err
	}
	if family == nil || family.Status != model.FamilyStatusNormal {
		return nil, ErrFamilyNotFound
	}

	dish, err := s.dishRepo.GetDishByID(ctx, dishID)
	if err != nil {
		return nil, err
	}
	if dish == nil {
		return nil, ErrMealPlanDishNotFound
	}

	if cookUserID != nil {
		cook, err := s.familyRepo.GetMember(ctx, familyID, *cookUserID)
		if err != nil {
			return nil, err
		}
		if cook == nil {
			return nil, ErrCookUserNotInFamily
		}
	}

	plan := &model.FamilyMealPlan{
		FamilyID:   familyID,
		DishID:     dishID,
		MealDate:   mealDate,
		MealType:   int8(mealType),
		Servings:   servings,
		CookUserID: cookUserID,
		Status:     model.MealPlanStatusPending,
		CreatedBy:  createdBy,
	}
	if err := s.mealPlanRepo.Create(ctx, plan); err != nil {
		return nil, err
	}
	return plan, nil
}
