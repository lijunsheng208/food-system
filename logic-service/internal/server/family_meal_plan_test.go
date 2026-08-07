package server

import (
	"testing"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/service"
)

func TestToFamilyMealPlanInfoPreservesOptionalCookUser(t *testing.T) {
	cookUserID := uint64(8)
	createdAt := time.Date(2026, 8, 5, 12, 30, 0, 0, time.Local)
	plan := &model.FamilyMealPlan{
		ID:         10,
		FamilyID:   2,
		DishID:     3,
		MealDate:   time.Date(2026, 8, 6, 0, 0, 0, 0, time.Local),
		MealType:   model.MealTypeDinner,
		Servings:   4,
		CookUserID: &cookUserID,
		Status:     model.MealPlanStatusPending,
		CreatedBy:  7,
		CreatedAt:  createdAt,
		UpdatedAt:  createdAt,
	}

	info := toFamilyMealPlanInfo(plan)
	if info.GetMealDate() != "2026-08-06" {
		t.Fatalf("meal_date = %q, want 2026-08-06", info.GetMealDate())
	}
	if info.CookUserId == nil || info.GetCookUserId() != 8 {
		t.Fatalf("cook_user_id = %v, want 8", info.CookUserId)
	}
}

func TestMapFamilyErrorCodeMapsMealPlanErrors(t *testing.T) {
	if got := mapFamilyErrorCode(service.ErrMealPlanDishNotFound); got != MealPlanCodeDishNotFound {
		t.Fatalf("dish error code = %d, want %d", got, MealPlanCodeDishNotFound)
	}
	if got := mapFamilyErrorCode(service.ErrCookUserNotInFamily); got != MealPlanCodeCookNotInFamily {
		t.Fatalf("cook error code = %d, want %d", got, MealPlanCodeCookNotInFamily)
	}
}
