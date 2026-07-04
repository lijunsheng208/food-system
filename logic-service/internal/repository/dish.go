package repository

import (
	"context"

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
