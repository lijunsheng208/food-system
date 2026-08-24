package service

import (
	"context"
	"errors"
	"fmt"
	"math"
	"strings"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
	"gorm.io/gorm"
)

// 购物清单业务错误。
var (
	ErrShoppingListNotFound = errors.New("购物清单不存在")
	ErrShoppingItemNotFound = errors.New("购物清单项目不存在")
	ErrInvalidShoppingDate  = errors.New("购物清单日期范围不正确")
	ErrInvalidShoppingName  = errors.New("购物清单名称不合法")
	ErrInvalidShoppingItem  = errors.New("购物项目不合法")
)

// ShoppingListService 负责购物清单生成、查询和项目维护。
type ShoppingListService struct {
	shoppingRepo *repository.ShoppingListRepo
	familyRepo   *repository.FamilyRepo
	mealPlanRepo *repository.MealPlanRepo
	dishRepo     *repository.DishRepo
}

// NewShoppingListService 创建购物清单 Service。
func NewShoppingListService(shoppingRepo *repository.ShoppingListRepo, familyRepo *repository.FamilyRepo, mealPlanRepo *repository.MealPlanRepo, dishRepo *repository.DishRepo) *ShoppingListService {
	return &ShoppingListService{shoppingRepo: shoppingRepo, familyRepo: familyRepo, mealPlanRepo: mealPlanRepo, dishRepo: dishRepo}
}

// ShoppingListResult 返回购物清单及其项目。
type ShoppingListResult struct {
	List  *model.ShoppingList
	Items []model.ShoppingListItem
}

// GenerateShoppingList 根据日期范围内的家庭菜单汇总食材并创建购物清单。
func (s *ShoppingListService) GenerateShoppingList(ctx context.Context, userID, familyID uint64, startDateText, endDateText, name string) (*ShoppingListResult, error) {
	if err := s.requireFamilyMember(ctx, userID, familyID); err != nil {
		return nil, err
	}
	startDate, endDate, err := parseShoppingDateRange(startDateText, endDateText)
	if err != nil {
		return nil, err
	}
	if name == "" {
		name = fmt.Sprintf("%s 至 %s 购物清单", startDateText, endDateText)
	}
	if len([]rune(name)) > 100 {
		return nil, ErrInvalidShoppingName
	}

	plans, err := s.mealPlanRepo.ListWithDetails(ctx, familyID, startDate, endDate)
	if err != nil {
		return nil, err
	}
	items, err := s.aggregateIngredients(ctx, plans)
	if err != nil {
		return nil, err
	}
	list, err := s.shoppingRepo.FindByFamilyDates(ctx, familyID, startDate, endDate)
	if err != nil {
		return nil, err
	}
	// 只从即将更新的目标清单继承购买进度，避免历史重复清单污染当前结果。
	if list != nil {
		_, previousItems, getErr := s.shoppingRepo.GetWithItems(ctx, list.ID)
		if getErr != nil {
			return nil, getErr
		}
		purchased := make(map[string]float64, len(previousItems))
		for _, item := range previousItems {
			if item.PurchasedQuantity > 0 || item.IsPurchased == model.ShoppingItemPurchased {
				value := item.PurchasedQuantity
				if value == 0 && item.IsPurchased == model.ShoppingItemPurchased && item.Quantity != nil {
					value = *item.Quantity
				}
				purchased[shoppingItemKey(item.IngredientName, item.Unit)] = value
			}
		}
		for index := range items {
			if value, ok := purchased[shoppingItemKey(items[index].IngredientName, items[index].Unit)]; ok {
				if items[index].Quantity != nil && value > *items[index].Quantity {
					value = *items[index].Quantity
				}
				items[index].PurchasedQuantity = value
				if items[index].Quantity != nil && value >= *items[index].Quantity {
					items[index].IsPurchased = model.ShoppingItemPurchased
				}
			}
		}
	}
	if list == nil {
		list = &model.ShoppingList{FamilyID: familyID, CreatedBy: userID, Name: name, StartDate: startDate, EndDate: endDate, Status: model.ShoppingListStatusActive}
		if err := s.shoppingRepo.CreateWithItems(ctx, list, items); err != nil {
			return nil, err
		}
	} else if err := s.shoppingRepo.ReplaceItems(ctx, list, items); err != nil {
		return nil, err
	}
	return &ShoppingListResult{List: list, Items: items}, nil
}

// shoppingItemKey 生成食材和单位匹配键，用于跨菜单数量变化继承购买进度。
func shoppingItemKey(name, unit string) string {
	return strings.TrimSpace(name) + "\x00" + strings.TrimSpace(unit)
}

// ListShoppingLists 查询当前用户所属家庭的购物清单。
func (s *ShoppingListService) ListShoppingLists(ctx context.Context, userID, familyID uint64) ([]model.ShoppingList, error) {
	if err := s.requireFamilyMember(ctx, userID, familyID); err != nil {
		return nil, err
	}
	return s.shoppingRepo.ListByFamily(ctx, familyID)
}

// GetShoppingList 查询清单详情，并校验当前用户仍属于该清单家庭。
func (s *ShoppingListService) GetShoppingList(ctx context.Context, userID, listID uint64) (*ShoppingListResult, error) {
	list, items, err := s.shoppingRepo.GetWithItems(ctx, listID)
	if err != nil {
		return nil, err
	}
	if list == nil {
		return nil, ErrShoppingListNotFound
	}
	if err := s.requireFamilyMember(ctx, userID, list.FamilyID); err != nil {
		return nil, err
	}
	return &ShoppingListResult{List: list, Items: items}, nil
}

// UpdateItemPurchased 更新清单项目的购买状态。
func (s *ShoppingListService) UpdateItemPurchased(ctx context.Context, userID, itemID uint64, purchasedQuantity float64, purchased bool) error {
	_, familyID, err := s.shoppingRepo.GetItemOwner(ctx, itemID)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return ErrShoppingItemNotFound
	}
	if err != nil {
		return err
	}
	if err := s.requireFamilyMember(ctx, userID, familyID); err != nil {
		return err
	}
	if purchasedQuantity < 0 {
		return ErrInvalidShoppingItem
	}
	if err := s.shoppingRepo.UpdateItemPurchased(ctx, itemID, purchasedQuantity, purchased); errors.Is(err, gorm.ErrRecordNotFound) {
		return ErrShoppingItemNotFound
	} else {
		return err
	}
}

// AddManualItem 向指定清单添加手动购物项目。
func (s *ShoppingListService) AddManualItem(ctx context.Context, userID, listID uint64, name string, quantity *float64, quantityText, unit string) (*model.ShoppingListItem, error) {
	if strings.TrimSpace(name) == "" || len([]rune(name)) > 100 || len([]rune(unit)) > 20 || len([]rune(quantityText)) > 50 || (quantity != nil && *quantity < 0) {
		return nil, ErrInvalidShoppingItem
	}
	list, items, err := s.shoppingRepo.GetWithItems(ctx, listID)
	if err != nil {
		return nil, err
	}
	if list == nil {
		return nil, ErrShoppingListNotFound
	}
	if err := s.requireFamilyMember(ctx, userID, list.FamilyID); err != nil {
		return nil, err
	}
	item := &model.ShoppingListItem{ShoppingListID: listID, IngredientName: strings.TrimSpace(name), Quantity: quantity, QuantityText: strings.TrimSpace(quantityText), Unit: strings.TrimSpace(unit), Source: "manual", SortOrder: len(items)}
	if err := s.shoppingRepo.CreateManualItem(ctx, item); err != nil {
		return nil, err
	}
	return item, nil
}

// DeleteItem 删除购物项目，并校验当前用户的家庭权限。
func (s *ShoppingListService) DeleteItem(ctx context.Context, userID, itemID uint64) error {
	_, familyID, err := s.shoppingRepo.GetItemOwner(ctx, itemID)
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return ErrShoppingItemNotFound
	}
	if err != nil {
		return err
	}
	if err := s.requireFamilyMember(ctx, userID, familyID); err != nil {
		return err
	}
	if err := s.shoppingRepo.DeleteItem(ctx, itemID); errors.Is(err, gorm.ErrRecordNotFound) {
		return ErrShoppingItemNotFound
	} else {
		return err
	}
}

// requireFamilyMember 校验操作者属于目标家庭，防止客户端伪造家庭 ID 访问数据。
func (s *ShoppingListService) requireFamilyMember(ctx context.Context, userID, familyID uint64) error {
	member, err := s.familyRepo.GetMember(ctx, familyID, userID)
	if err != nil {
		return err
	}
	if member == nil {
		return ErrUserNotInFamily
	}
	return nil
}

// aggregateIngredients 将菜单食材按名称和单位合并，文本用量单独保留不参与数值相加。
func (s *ShoppingListService) aggregateIngredients(ctx context.Context, plans []model.FamilyMealPlanView) ([]model.ShoppingListItem, error) {
	dishes := make(map[uint64]model.Dish, len(plans))
	ingredientsByDish := make(map[uint64][]model.DishIngredient, len(plans))
	for _, plan := range plans {
		dish, err := s.dishRepo.GetDishByID(ctx, plan.DishID)
		if err != nil {
			return nil, err
		}
		if dish == nil {
			continue
		}
		ingredients, err := s.dishRepo.ListIngredientsByDishID(ctx, plan.DishID)
		if err != nil {
			return nil, err
		}
		dishes[plan.DishID] = *dish
		ingredientsByDish[plan.DishID] = ingredients
	}
	return aggregateShoppingIngredients(plans, dishes, ingredientsByDish), nil
}

// aggregateShoppingIngredients 按食材名称和单位汇总菜单食材，不跨单位进行换算。
func aggregateShoppingIngredients(plans []model.FamilyMealPlanView, dishes map[uint64]model.Dish, ingredientsByDish map[uint64][]model.DishIngredient) []model.ShoppingListItem {
	type aggregate struct {
		item  model.ShoppingListItem
		value float64
	}
	groups := make(map[string]*aggregate)
	order := make([]string, 0)
	for _, plan := range plans {
		dish, ok := dishes[plan.DishID]
		if !ok {
			continue
		}
		scale := float64(plan.Servings)
		if dish.Servings > 0 {
			scale /= float64(dish.Servings)
		}
		for _, ingredient := range ingredientsByDish[plan.DishID] {
			name := strings.TrimSpace(ingredient.Name)
			unit := strings.TrimSpace(ingredient.Unit)
			if name == "" {
				continue
			}
			key := name + "\x00" + unit
			if ingredient.Amount == nil || strings.TrimSpace(ingredient.AmountText) != "" {
				key += "\x00text\x00" + strings.TrimSpace(ingredient.AmountText)
			}
			entry, ok := groups[key]
			if !ok {
				entry = &aggregate{item: model.ShoppingListItem{IngredientName: name, Unit: unit, QuantityText: strings.TrimSpace(ingredient.AmountText), Source: "meal_plan", SortOrder: len(order)}}
				groups[key] = entry
				order = append(order, key)
			}
			if ingredient.Amount != nil && strings.TrimSpace(ingredient.AmountText) == "" {
				entry.value += *ingredient.Amount * scale
				value := math.Round(entry.value*100) / 100
				entry.item.Quantity = &value
			}
		}
	}
	items := make([]model.ShoppingListItem, 0, len(order))
	for _, key := range order {
		items = append(items, groups[key].item)
	}
	return items
}

// parseShoppingDateRange 解析并校验购物清单的日期范围。
func parseShoppingDateRange(startText, endText string) (time.Time, time.Time, error) {
	start, err := repository.ParseShoppingDate(startText)
	if err != nil {
		return time.Time{}, time.Time{}, ErrInvalidShoppingDate
	}
	end, err := repository.ParseShoppingDate(endText)
	if err != nil || end.Before(start) {
		return time.Time{}, time.Time{}, ErrInvalidShoppingDate
	}
	return start, end, nil
}
