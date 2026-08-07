package model

import "time"

// FamilyMealPlan 家庭菜单计划表模型。
type FamilyMealPlan struct {
	ID         uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	FamilyID   uint64    `gorm:"column:family_id;not null;index:idx_family_date,priority:1" json:"family_id"`
	DishID     uint64    `gorm:"column:dish_id;not null;index:idx_dish" json:"dish_id"`
	MealDate   time.Time `gorm:"column:meal_date;type:date;not null;index:idx_family_date,priority:2" json:"meal_date"`
	MealType   int8      `gorm:"column:meal_type;type:tinyint;not null" json:"meal_type"`
	Servings   int       `gorm:"column:servings;not null;default:1" json:"servings"`
	CookUserID *uint64   `gorm:"column:cook_user_id;index:idx_cook_user" json:"cook_user_id"`
	Status     int8      `gorm:"column:status;type:tinyint;not null;default:0" json:"status"`
	CreatedBy  uint64    `gorm:"column:created_by;not null" json:"created_by"`
	CreatedAt  time.Time `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt  time.Time `gorm:"column:updated_at;not null" json:"updated_at"`
}

// FamilyMealPlanView 是菜单列表所需的菜谱和负责人联表结果。
type FamilyMealPlanView struct {
	FamilyMealPlan
	DishName     string `gorm:"column:dish_name" json:"dish_name"`
	DishImageKey string `gorm:"column:dish_image_key" json:"dish_image_key"`
	CookUserName string `gorm:"column:cook_user_name" json:"cook_user_name"`
}

func (FamilyMealPlan) TableName() string {
	return "family_meal_plan"
}

const (
	MealTypeBreakfast int8 = 1
	MealTypeLunch     int8 = 2
	MealTypeDinner    int8 = 3
)

const (
	MealPlanStatusPending   int8 = 0
	MealPlanStatusCooking   int8 = 1
	MealPlanStatusCompleted int8 = 2
	MealPlanStatusCancelled int8 = 3
)
