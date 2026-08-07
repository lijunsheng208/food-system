package service

import (
	"context"
	"errors"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
)

var (
	ErrInvalidMealPlanIDs   = errors.New("家庭、菜谱、创建人和负责人ID必须有效")
	ErrInvalidMealDate      = errors.New("用餐日期格式不正确")
	ErrInvalidMealType      = errors.New("餐次类型不正确")
	ErrInvalidMealServings  = errors.New("用餐人数必须在1到20之间")
	ErrMealPlanDishNotFound = errors.New("菜谱不存在或已下架")
	ErrCookUserNotInFamily  = errors.New("做饭负责人不是该家庭成员")
	ErrMealPlanNotFound     = errors.New("家庭菜单记录不存在")
	ErrInvalidMealDateRange = errors.New("日期范围不正确")
)

// MealPlanService 家庭菜单计划业务逻辑。
type MealPlanService struct {
	mealPlanRepo *repository.MealPlanRepo
	familyRepo   *repository.FamilyRepo
	dishRepo     *repository.DishRepo
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

func (s *MealPlanService) UpdateMealPlan(ctx context.Context, id, userID uint64, mealDateText *string, mealType *int32, servings *int, cookUserID *uint64) (*model.FamilyMealPlan, error) {
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
	if len(values) > 0 {
		if err := s.mealPlanRepo.Update(ctx, id, values); err != nil {
			return nil, err
		}
		plan.UpdatedAt = time.Now()
	}
	return plan, nil
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
