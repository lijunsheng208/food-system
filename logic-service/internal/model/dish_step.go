package model

import "time"

// DishStep 菜谱制作步骤表模型
type DishStep struct {
	ID           uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	DishID       uint64    `gorm:"column:dish_id;not null;index:idx_dish_step_dish;uniqueIndex:uk_dish_step_no,priority:1" json:"dish_id"`
	StepNo       int       `gorm:"column:step_no;not null;uniqueIndex:uk_dish_step_no,priority:2" json:"step_no"`
	Description  string    `gorm:"column:description;type:text;not null" json:"description"`
	TimerSeconds int       `gorm:"column:timer_seconds;not null;default:0" json:"timer_seconds"`
	ImageKey     string    `gorm:"column:image_key;type:varchar(255);not null;default:''" json:"image_key"`
	CreatedAt    time.Time `gorm:"column:created_at" json:"created_at"`
	UpdatedAt    time.Time `gorm:"column:updated_at" json:"updated_at"`
}

func (DishStep) TableName() string {
	return "dish_step"
}
