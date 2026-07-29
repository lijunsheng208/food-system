package service

import (
	"testing"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
)

func TestGroupIngredientsPreservesQueryOrder(t *testing.T) {
	ingredients := []model.DishIngredient{
		{ID: 1, GroupName: "主料", Name: "五花肉"},
		{ID: 2, GroupName: "调料", Name: "生抽"},
		{ID: 3, GroupName: "主料", Name: "鸡蛋"},
	}

	groups := groupIngredients(ingredients)
	if len(groups) != 2 {
		t.Fatalf("group count = %d, want 2", len(groups))
	}
	if groups[0].Name != "主料" || len(groups[0].Ingredients) != 2 {
		t.Fatalf("first group = %#v, want 主料 with two ingredients", groups[0])
	}
	if groups[0].Ingredients[1].Name != "鸡蛋" {
		t.Fatalf("second 主料 ingredient = %q, want 鸡蛋", groups[0].Ingredients[1].Name)
	}
	if groups[1].Name != "调料" || len(groups[1].Ingredients) != 1 {
		t.Fatalf("second group = %#v, want 调料 with one ingredient", groups[1])
	}
}

func TestGroupIngredientsReturnsEmptySlice(t *testing.T) {
	groups := groupIngredients(nil)
	if groups == nil {
		t.Fatal("groupIngredients(nil) returned nil, want empty slice")
	}
	if len(groups) != 0 {
		t.Fatalf("group count = %d, want 0", len(groups))
	}
}
