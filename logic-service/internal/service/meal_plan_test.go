package service

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestParseMealDateUsesUTCWithoutChangingCalendarDate(t *testing.T) {
	date, err := parseMealDate("2026-08-05")
	if err != nil {
		t.Fatalf("parseMealDate() error = %v", err)
	}
	if date.Location() != time.UTC {
		t.Fatalf("location = %v, want UTC", date.Location())
	}
	if got := date.Format("2006-01-02"); got != "2026-08-05" {
		t.Fatalf("date = %q, want 2026-08-05", got)
	}
}

func TestCreateMealPlanRejectsInvalidInputBeforeRepositoryAccess(t *testing.T) {
	tests := []struct {
		name       string
		familyID   uint64
		dishID     uint64
		mealDate   string
		mealType   int32
		servings   int
		cookUserID *uint64
		createdBy  uint64
		wantErr    error
	}{
		{name: "invalid ids", dishID: 1, mealDate: "2026-08-05", mealType: 3, servings: 2, createdBy: 1, wantErr: ErrInvalidMealPlanIDs},
		{name: "invalid date", familyID: 1, dishID: 1, mealDate: "2026/08/05", mealType: 3, servings: 2, createdBy: 1, wantErr: ErrInvalidMealDate},
		{name: "invalid meal type", familyID: 1, dishID: 1, mealDate: "2026-08-05", mealType: 4, servings: 2, createdBy: 1, wantErr: ErrInvalidMealType},
		{name: "invalid servings", familyID: 1, dishID: 1, mealDate: "2026-08-05", mealType: 3, servings: 21, createdBy: 1, wantErr: ErrInvalidMealServings},
	}

	svc := &MealPlanService{}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := svc.CreateMealPlan(
				context.Background(),
				tt.familyID,
				tt.dishID,
				tt.mealDate,
				tt.mealType,
				tt.servings,
				tt.cookUserID,
				tt.createdBy,
			)
			if !errors.Is(err, tt.wantErr) {
				t.Fatalf("CreateMealPlan() error = %v, want %v", err, tt.wantErr)
			}
		})
	}
}
