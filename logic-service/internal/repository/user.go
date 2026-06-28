package repository

import (
	"context"
	"errors"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
)

// UserRepo 用户数据访问
type UserRepo struct {
	db *gorm.DB
}

// NewUserRepo 创建 UserRepo
func NewUserRepo(db *gorm.DB) *UserRepo {
	return &UserRepo{db: db}
}

// FindByPhone 按手机号查询用户
func (r *UserRepo) FindByPhone(ctx context.Context, phone string) (*model.User, error) {
	var user model.User
	err := r.db.WithContext(ctx).Where("phone = ?", phone).First(&user).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &user, nil
}

// Create 创建用户
func (r *UserRepo) Create(ctx context.Context, user *model.User) error {
	return r.db.WithContext(ctx).Create(user).Error
}

// UpdateLastLogin 更新最后登录时间
func (r *UserRepo) UpdateLastLogin(ctx context.Context, userID uint64) error {
	now := time.Now()
	return r.db.WithContext(ctx).
		Model(&model.User{}).
		Where("id = ?", userID).
		Update("last_login_at", &now).Error
}
