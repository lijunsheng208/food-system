package server

import (
	"testing"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/service"
)

func TestToDishDetailInfoPreservesOptionalAmountAndTimer(t *testing.T) {
	amount := 500.0
	detail := &service.DishDetail{
		Dish: &model.Dish{
			ID:          1,
			CategoryID:  2,
			Name:        "红烧肉",
			CookMinutes: 45,
			Difficulty:  2,
			Servings:    3,
		},
		IngredientGroups: []service.DishIngredientGroup{
			{
				Name: "主料",
				Ingredients: []model.DishIngredient{
					{ID: 1, Name: "五花肉", Amount: &amount, Unit: "克"},
					{ID: 2, Name: "盐", AmountText: "适量"},
				},
			},
		},
		Steps: []model.DishStep{{
			ID:           10,
			StepNo:       1,
			Description:  "小火炖煮",
			TimerSeconds: 1800,
		}},
	}

	info := toDishDetailInfo(detail)
	if len(info.Steps) != 1 {
		t.Fatalf("steps count = %d, want 1", len(info.Steps))
	}
	if info.Steps[0].GetTimerSeconds() != 1800 {
		t.Fatalf("timer_seconds = %d, want 1800", info.Steps[0].GetTimerSeconds())
	}
	ingredients := info.IngredientGroups[0].Ingredients
	if ingredients[0].Amount == nil || ingredients[0].GetAmount() != 500 {
		t.Fatalf("numeric amount = %v, want 500", ingredients[0].Amount)
	}
	if ingredients[1].Amount != nil {
		t.Fatalf("text amount = %v, want nil", ingredients[1].Amount)
	}
}
