package repository

import (
	"context"
	"errors"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
)

// MealPlanRepo 家庭菜单计划数据访问。
type MealPlanRepo struct {
	db *gorm.DB
}

func NewMealPlanRepo(db *gorm.DB) *MealPlanRepo {
	return &MealPlanRepo{db: db}
}

// Create 创建家庭菜单计划。
func (r *MealPlanRepo) Create(ctx context.Context, plan *model.FamilyMealPlan) error {
	return r.db.WithContext(ctx).Create(plan).Error
}

func (r *MealPlanRepo) GetByID(ctx context.Context, id uint64) (*model.FamilyMealPlan, error) {
	var plan model.FamilyMealPlan
	err := r.db.WithContext(ctx).First(&plan, id).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}
	return &plan, err
}

func (r *MealPlanRepo) ListWithDetails(ctx context.Context, familyID uint64, startDate, endDate time.Time) ([]model.FamilyMealPlanView, error) {
	var plans []model.FamilyMealPlanView
	err := r.db.WithContext(ctx).
		Table("family_meal_plan AS p").
		Select(`p.*, d.name AS dish_name, d.image_key AS dish_image_key,
			COALESCE(NULLIF(fm.display_name, ''), u.nickname, '') AS cook_user_name`).
		Joins("JOIN dish AS d ON d.id = p.dish_id").
		Joins("LEFT JOIN users AS u ON u.id = p.cook_user_id").
		Joins("LEFT JOIN family_members AS fm ON fm.family_id = p.family_id AND fm.user_id = p.cook_user_id").
		Where("p.family_id = ? AND p.meal_date BETWEEN ? AND ?", familyID, startDate, endDate).
		Order("p.meal_date ASC, p.meal_type ASC, p.id ASC").
		Scan(&plans).Error
	return plans, err
}

func (r *MealPlanRepo) Update(ctx context.Context, id uint64, values map[string]any) error {
	return r.db.WithContext(ctx).Model(&model.FamilyMealPlan{}).Where("id = ?", id).Updates(values).Error
}

func (r *MealPlanRepo) Delete(ctx context.Context, id uint64) error {
	return r.db.WithContext(ctx).Delete(&model.FamilyMealPlan{}, id).Error
}
