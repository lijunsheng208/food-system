package model

import "time"

// Dish 菜谱表模型
type Dish struct {
	ID          uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	CategoryID  uint64    `gorm:"column:category_id;not null;index:idx_category" json:"category_id"`
	Name        string    `gorm:"column:name;type:varchar(100);not null" json:"name"`
	Description *string   `gorm:"column:description;type:varchar(500)" json:"description"`
	ImageKey    string    `gorm:"column:image_key;type:varchar(255);not null" json:"image_key"`
	Status      int8      `gorm:"column:status;type:tinyint;default:1" json:"status"`
	Sort        int       `gorm:"column:sort;type:int;default:0" json:"sort"`
	CreatedAt   time.Time `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt   time.Time `gorm:"column:updated_at;not null" json:"updated_at"`
}

func (Dish) TableName() string {
	return "dish"
}

// 菜谱状态常量
const (
	DishStatusOnSale  int8 = 1 // 上架
	DishStatusOffSale int8 = 0 // 下架
)
