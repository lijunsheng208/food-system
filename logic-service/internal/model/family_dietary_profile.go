package model

import "time"

// FamilyDietaryProfile 保存家庭级预算和整体饮食说明。
type FamilyDietaryProfile struct {
	ID             uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	FamilyID       uint64    `gorm:"column:family_id;not null;uniqueIndex" json:"family_id"`
	BudgetMin      *float64  `gorm:"column:budget_min;type:decimal(10,2)" json:"budget_min"`
	BudgetMax      *float64  `gorm:"column:budget_max;type:decimal(10,2)" json:"budget_max"`
	BudgetCurrency string    `gorm:"column:budget_currency;type:varchar(10);not null" json:"budget_currency"`
	BudgetPeriod   int8      `gorm:"column:budget_period;not null" json:"budget_period"`
	Notes          string    `gorm:"column:notes;type:varchar(500);not null" json:"notes"`
	UpdatedBy      uint64    `gorm:"column:updated_by;not null" json:"updated_by"`
	CreatedAt      time.Time `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt      time.Time `gorm:"column:updated_at;not null" json:"updated_at"`
}

// TableName 指定家庭饮食档案表名。
func (FamilyDietaryProfile) TableName() string { return "family_dietary_profile" }

const (
	// DietaryBudgetDaily 表示按天设置预算。
	DietaryBudgetDaily int8 = 1
	// DietaryBudgetWeekly 表示按周设置预算。
	DietaryBudgetWeekly int8 = 2
	// DietaryBudgetMonthly 表示按月设置预算。
	DietaryBudgetMonthly int8 = 3
)
