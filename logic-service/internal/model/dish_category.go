package model

import "time"

// DishCategory 菜谱分类表模型
type DishCategory struct {
	ID        uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	Name      string    `gorm:"column:name;type:varchar(50);not null" json:"name"`
	Sort      int       `gorm:"column:sort;type:int;default:0" json:"sort"`
	Status    int8      `gorm:"column:status;type:tinyint;default:1" json:"status"`
	CreatedAt time.Time `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt time.Time `gorm:"column:updated_at;not null" json:"updated_at"`
}

func (DishCategory) TableName() string {
	return "dish_category"
}

// 分类状态常量
const (
	DishCategoryStatusNormal   int8 = 1 // 正常
	DishCategoryStatusDisabled int8 = 0 // 禁用
)
