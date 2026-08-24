package repository

import (
	"context"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
)

// UserDietaryPreferenceRepo 负责用户个人饮食偏好的持久化。
type UserDietaryPreferenceRepo struct {
	db *gorm.DB
}

// NewUserDietaryPreferenceRepo 创建用户饮食偏好仓储。
func NewUserDietaryPreferenceRepo(db *gorm.DB) *UserDietaryPreferenceRepo {
	return &UserDietaryPreferenceRepo{db: db}
}

// ListByUser 查询指定用户的全部饮食偏好，并按类型和创建顺序稳定返回。
func (r *UserDietaryPreferenceRepo) ListByUser(ctx context.Context, userID uint64) ([]model.UserDietaryPreference, error) {
	var preferences []model.UserDietaryPreference
	err := r.db.WithContext(ctx).
		Where("user_id = ?", userID).
		Order("preference_type ASC, id ASC").
		Find(&preferences).Error
	return preferences, err
}

// ReplaceByUser 在一个事务中替换用户全部偏好，保证保存失败时不会留下半套数据。
func (r *UserDietaryPreferenceRepo) ReplaceByUser(ctx context.Context, userID uint64, preferences []model.UserDietaryPreference) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("user_id = ?", userID).Delete(&model.UserDietaryPreference{}).Error; err != nil {
			return err
		}
		if len(preferences) == 0 {
			return nil
		}
		now := time.Now()
		for index := range preferences {
			preferences[index].UserID = userID
			if preferences[index].CreatedAt.IsZero() {
				preferences[index].CreatedAt = now
			}
			if preferences[index].UpdatedAt.IsZero() {
				preferences[index].UpdatedAt = preferences[index].CreatedAt
			}
		}
		return tx.Create(&preferences).Error
	})
}
