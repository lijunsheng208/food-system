package model

import "time"

// DishIngredient 菜谱食材表模型
type DishIngredient struct {
	ID         uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	DishID     uint64    `gorm:"column:dish_id;not null;index:idx_dish_ingredient_order,priority:1" json:"dish_id"`
	GroupName  string    `gorm:"column:group_name;type:varchar(50);not null;default:''" json:"group_name"`
	GroupSort  int       `gorm:"column:group_sort;type:int;not null;default:0;index:idx_dish_ingredient_order,priority:2" json:"group_sort"`
	Name       string    `gorm:"column:name;type:varchar(100);not null" json:"name"`
	Amount     *float64  `gorm:"column:amount;type:decimal(10,2)" json:"amount"`
	AmountText string    `gorm:"column:amount_text;type:varchar(50);not null;default:''" json:"amount_text"`
	Unit       string    `gorm:"column:unit;type:varchar(20);not null;default:''" json:"unit"`
	Sort       int       `gorm:"column:sort;type:int;not null;default:0;index:idx_dish_ingredient_order,priority:3" json:"sort"`
	CreatedAt  time.Time `gorm:"column:created_at" json:"created_at"`
	UpdatedAt  time.Time `gorm:"column:updated_at" json:"updated_at"`
}

func (DishIngredient) TableName() string {
	return "dish_ingredient"
}
