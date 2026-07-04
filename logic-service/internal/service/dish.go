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
)

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
