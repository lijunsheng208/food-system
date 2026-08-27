package model

import "time"

// FamilyMealPlanRating 家庭成员对某次家庭菜单的评价。
type FamilyMealPlanRating struct {
	ID         uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	MealPlanID uint64    `gorm:"column:meal_plan_id;not null" json:"meal_plan_id"`
	UserID     uint64    `gorm:"column:user_id;not null" json:"user_id"`
	Rating     int8      `gorm:"column:rating;not null" json:"rating"`
	Comment    string    `gorm:"column:comment" json:"comment"`
	CreatedAt  time.Time `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt  time.Time `gorm:"column:updated_at;not null" json:"updated_at"`
}

// TableName 返回家庭菜单评价表名。
func (FamilyMealPlanRating) TableName() string { return "family_meal_plan_rating" }

// FamilyMealPlanRatingView 包含评价用户昵称的评价视图。
type FamilyMealPlanRatingView struct {
	FamilyMealPlanRating
	UserName string `gorm:"column:user_name" json:"user_name"`
}
