package repository

import (
	"context"
	"errors"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
)

// FamilyDietaryProfileRepo 负责家庭饮食档案的持久化。
type FamilyDietaryProfileRepo struct{ db *gorm.DB }

// NewFamilyDietaryProfileRepo 创建家庭饮食档案仓储。
func NewFamilyDietaryProfileRepo(db *gorm.DB) *FamilyDietaryProfileRepo {
	return &FamilyDietaryProfileRepo{db: db}
}

// GetByFamily 查询家庭饮食档案，不存在时返回 nil。
func (r *FamilyDietaryProfileRepo) GetByFamily(ctx context.Context, familyID uint64) (*model.FamilyDietaryProfile, error) {
	var profile model.FamilyDietaryProfile
	err := r.db.WithContext(ctx).Where("family_id = ?", familyID).First(&profile).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &profile, nil
}

// Save 保存家庭饮食档案，使用唯一家庭键实现创建或更新。
func (r *FamilyDietaryProfileRepo) Save(ctx context.Context, profile *model.FamilyDietaryProfile) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var existing model.FamilyDietaryProfile
		err := tx.Where("family_id = ?", profile.FamilyID).First(&existing).Error
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return tx.Create(profile).Error
		}
		if err != nil {
			return err
		}
		profile.ID = existing.ID
		profile.CreatedAt = existing.CreatedAt
		return tx.Model(&existing).Updates(map[string]interface{}{
			"budget_min": profile.BudgetMin, "budget_max": profile.BudgetMax,
			"budget_currency": profile.BudgetCurrency, "budget_period": profile.BudgetPeriod,
			"notes": profile.Notes, "updated_by": profile.UpdatedBy,
		}).Error
	})
}
