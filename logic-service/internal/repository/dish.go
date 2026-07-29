package repository

import (
	"context"
	"errors"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
)

// DishRepo 菜谱数据访问
type DishRepo struct {
	db *gorm.DB
}

// NewDishRepo 创建 DishRepo
func NewDishRepo(db *gorm.DB) *DishRepo {
	return &DishRepo{db: db}
}

// ListCategories 查询所有启用的分类，按 sort 升序
func (r *DishRepo) ListCategories(ctx context.Context) ([]model.DishCategory, error) {
	var categories []model.DishCategory
	err := r.db.WithContext(ctx).
		Where("status = ?", model.DishCategoryStatusNormal).
		Order("sort ASC, id ASC").
		Find(&categories).Error
	return categories, err
}

// ListDishesByCategory 根据分类查询上架的菜谱，按 sort 升序
func (r *DishRepo) ListDishesByCategory(ctx context.Context, categoryID uint64) ([]model.Dish, error) {
	var dishes []model.Dish
	err := r.db.WithContext(ctx).
		Where("category_id = ? AND status = ?", categoryID, model.DishStatusOnSale).
		Order("sort ASC, id ASC").
		Find(&dishes).Error
	return dishes, err
}

// SearchDishes 按关键字搜索上架菜谱名称
func (r *DishRepo) SearchDishes(ctx context.Context, keyword string) ([]model.Dish, error) {
	var dishes []model.Dish
	err := r.db.WithContext(ctx).
		Where("name LIKE ? AND status = ?", "%"+keyword+"%", model.DishStatusOnSale).
		Order("sort ASC, id ASC").
		Find(&dishes).Error
	return dishes, err
}

// GetDishByID 查询已上架的菜谱详情基础信息
func (r *DishRepo) GetDishByID(ctx context.Context, dishID uint64) (*model.Dish, error) {
	var dish model.Dish
	err := r.db.WithContext(ctx).
		Where("id = ? AND status = ?", dishID, model.DishStatusOnSale).
		First(&dish).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &dish, nil
}

// ListIngredientsByDishID 查询菜谱食材，按分组和组内顺序排列
func (r *DishRepo) ListIngredientsByDishID(ctx context.Context, dishID uint64) ([]model.DishIngredient, error) {
	var ingredients []model.DishIngredient
	err := r.db.WithContext(ctx).
		Where("dish_id = ?", dishID).
		Order("group_sort ASC, sort ASC, id ASC").
		Find(&ingredients).Error
	return ingredients, err
}

// ListStepsByDishID 查询菜谱制作步骤
func (r *DishRepo) ListStepsByDishID(ctx context.Context, dishID uint64) ([]model.DishStep, error) {
	var steps []model.DishStep
	err := r.db.WithContext(ctx).
		Where("dish_id = ?", dishID).
		Order("step_no ASC, id ASC").
		Find(&steps).Error
	return steps, err
}
