package repository

import (
	"context"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
)

// FamilyMealPlanRatingRepo 家庭菜单评价数据访问。
type FamilyMealPlanRatingRepo struct{ db *gorm.DB }

// NewFamilyMealPlanRatingRepo 创建家庭菜单评价仓储。
func NewFamilyMealPlanRatingRepo(db *gorm.DB) *FamilyMealPlanRatingRepo {
	return &FamilyMealPlanRatingRepo{db: db}
}

// GetByMealPlanUser 查询用户对某次菜单的评价。
func (r *FamilyMealPlanRatingRepo) GetByMealPlanUser(ctx context.Context, mealPlanID, userID uint64) (*model.FamilyMealPlanRating, error) {
	var value model.FamilyMealPlanRating
	err := r.db.WithContext(ctx).Where("meal_plan_id = ? AND user_id = ?", mealPlanID, userID).First(&value).Error
	if err == gorm.ErrRecordNotFound {
		return nil, nil
	}
	return &value, err
}

// Save 保存或更新评价，唯一键保证同一用户不会产生重复评价。
func (r *FamilyMealPlanRatingRepo) Save(ctx context.Context, value *model.FamilyMealPlanRating) error {
	return r.db.WithContext(ctx).Save(value).Error
}

// ListByMealPlan 查询某次菜单的全部家庭成员评价。
func (r *FamilyMealPlanRatingRepo) ListByMealPlan(ctx context.Context, mealPlanID uint64) ([]model.FamilyMealPlanRatingView, error) {
	var values []model.FamilyMealPlanRatingView
	err := r.db.WithContext(ctx).
		Table("family_meal_plan_rating AS r").
		Select("r.*, COALESCE(u.nickname, '') AS user_name").
		Joins("LEFT JOIN users AS u ON u.id = r.user_id").
		Where("r.meal_plan_id = ?", mealPlanID).
		Order("r.created_at DESC").Scan(&values).Error
	return values, err
}
