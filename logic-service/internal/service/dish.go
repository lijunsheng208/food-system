package service

import (
	"context"
	"errors"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/repository"
)

// 业务错误
var (
	ErrCategoryNotFound = errors.New("分类不存在")
	ErrDishNotFound     = errors.New("菜谱不存在")
)

// DishIngredientGroup 菜谱食材分组
type DishIngredientGroup struct {
	Name        string
	Ingredients []model.DishIngredient
}

// DishDetail 菜谱详情
type DishDetail struct {
	Dish             *model.Dish
	IngredientGroups []DishIngredientGroup
	Steps            []model.DishStep
}

// DishService 菜谱业务逻辑
type DishService struct {
	dishRepo *repository.DishRepo
}

// NewDishService 创建 DishService
func NewDishService(dishRepo *repository.DishRepo) *DishService {
	return &DishService{dishRepo: dishRepo}
}

// ListCategories 查询分类列表
func (s *DishService) ListCategories(ctx context.Context) ([]model.DishCategory, error) {
	return s.dishRepo.ListCategories(ctx)
}

// ListDishesByCategory 根据分类查询菜谱
func (s *DishService) ListDishesByCategory(ctx context.Context, categoryID uint64) ([]model.Dish, error) {
	return s.dishRepo.ListDishesByCategory(ctx, categoryID)
}

// SearchDishes 按关键字搜索菜谱
func (s *DishService) SearchDishes(ctx context.Context, keyword string) ([]model.Dish, error) {
	return s.dishRepo.SearchDishes(ctx, keyword)
}

// GetDishDetail 查询菜谱详情、食材分组和制作步骤
func (s *DishService) GetDishDetail(ctx context.Context, dishID uint64) (*DishDetail, error) {
	dish, err := s.dishRepo.GetDishByID(ctx, dishID)
	if err != nil {
		return nil, err
	}
	if dish == nil {
		return nil, ErrDishNotFound
	}

	ingredients, err := s.dishRepo.ListIngredientsByDishID(ctx, dishID)
	if err != nil {
		return nil, err
	}
	steps, err := s.dishRepo.ListStepsByDishID(ctx, dishID)
	if err != nil {
		return nil, err
	}

	return &DishDetail{
		Dish:             dish,
		IngredientGroups: groupIngredients(ingredients),
		Steps:            steps,
	}, nil
}

func groupIngredients(ingredients []model.DishIngredient) []DishIngredientGroup {
	groups := make([]DishIngredientGroup, 0)
	groupIndexes := make(map[string]int)

	for _, ingredient := range ingredients {
		index, ok := groupIndexes[ingredient.GroupName]
		if !ok {
			index = len(groups)
			groupIndexes[ingredient.GroupName] = index
			groups = append(groups, DishIngredientGroup{
				Name:        ingredient.GroupName,
				Ingredients: make([]model.DishIngredient, 0),
			})
		}
		groups[index].Ingredients = append(groups[index].Ingredients, ingredient)
	}

	return groups
}
