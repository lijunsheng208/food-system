package model

import "time"

// User 用户表模型
type User struct {
	ID           uint64     `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	Phone        string     `gorm:"column:phone;type:varchar(20);uniqueIndex:uk_phone;not null" json:"phone"`
	PasswordHash *string    `gorm:"column:password_hash;type:varchar(255)" json:"-"`
	Nickname     string     `gorm:"column:nickname;type:varchar(50);not null" json:"nickname"`
	Avatar       *string    `gorm:"column:avatar;type:varchar(500)" json:"avatar"`
	Gender       int8       `gorm:"column:gender;type:tinyint;default:0" json:"gender"`
	Status       int8       `gorm:"column:status;type:tinyint;default:1;not null" json:"status"`
	LastLoginAt  *time.Time `gorm:"column:last_login_at" json:"last_login_at"`
	CreatedAt    time.Time  `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt    time.Time  `gorm:"column:updated_at;not null" json:"updated_at"`
}

// TableName 指定表名
func (User) TableName() string {
	return "users"
}

// 用户状态常量
const (
	UserStatusNormal   int8 = 1 // 正常
	UserStatusDisabled int8 = 2 // 禁用
)

// 性别常量
const (
	GenderUnknown int8 = 0 // 未知
	GenderMale    int8 = 1 // 男
	GenderFemale  int8 = 2 // 女
)
