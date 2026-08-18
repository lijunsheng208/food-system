package service

import (
	"testing"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
)

// TestAggregateShoppingIngredients 验证购物清单的食材合并规则。
func TestAggregateShoppingIngredients(t *testing.T) {
	eggs := 3.0
	tomatoes := 2.0
	grams := 200.0
	plans := []model.FamilyMealPlanView{
		{FamilyMealPlan: model.FamilyMealPlan{DishID: 1, Servings: 2}},
		{FamilyMealPlan: model.FamilyMealPlan{DishID: 2, Servings: 2}},
	}
	dishes := map[uint64]model.Dish{
		1: {ID: 1, Servings: 2},
		2: {ID: 2, Servings: 2},
	}
	ingredients := map[uint64][]model.DishIngredient{
		1: {{Name: "鸡蛋", Amount: &eggs, Unit: "个"}, {Name: "番茄", Amount: &tomatoes, Unit: "个"}},
		2: {{Name: "鸡蛋", Amount: &eggs, Unit: "个"}, {Name: "番茄", Amount: &grams, Unit: "克"}},
	}

	items := aggregateShoppingIngredients(plans, dishes, ingredients)
	if len(items) != 3 {
		t.Fatalf("got %d items, want 3", len(items))
	}
	if items[0].IngredientName != "鸡蛋" || items[0].Quantity == nil || *items[0].Quantity != 6 {
		t.Fatalf("eggs = %#v, want 6 个", items[0])
	}
	if items[1].IngredientName != "番茄" || items[1].Unit != "个" || items[1].Quantity == nil || *items[1].Quantity != 2 {
		t.Fatalf("tomatoes = %#v, want 2 个", items[1])
	}
	if items[2].IngredientName != "番茄" || items[2].Unit != "克" || items[2].Quantity == nil || *items[2].Quantity != 200 {
		t.Fatalf("tomatoes grams = %#v, want 200 克", items[2])
	}
}

// TestAggregateShoppingIngredientsKeepsTextQuantity 验证文本用量不会被当作数值相加。
func TestAggregateShoppingIngredientsKeepsTextQuantity(t *testing.T) {
	plans := []model.FamilyMealPlanView{{FamilyMealPlan: model.FamilyMealPlan{DishID: 1, Servings: 2}}}
	dishes := map[uint64]model.Dish{1: {ID: 1, Servings: 2}}
	ingredients := map[uint64][]model.DishIngredient{1: {{Name: "食用油", AmountText: "适量", Unit: ""}}}
	items := aggregateShoppingIngredients(plans, dishes, ingredients)
	if len(items) != 1 || items[0].Quantity != nil || items[0].QuantityText != "适量" {
		t.Fatalf("text quantity = %#v, want 适量 without numeric quantity", items)
	}
}
