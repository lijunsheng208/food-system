package model

import "time"

// UserDietaryPreference 保存用户长期有效的个人饮食偏好，不依赖当前家庭成员关系。
type UserDietaryPreference struct {
	ID              uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	UserID          uint64    `gorm:"column:user_id;not null;uniqueIndex:uk_user_dietary_preference,priority:1;index:idx_user_dietary_preference_type,priority:1" json:"user_id"`
	PreferenceType  int8      `gorm:"column:preference_type;type:tinyint;not null;uniqueIndex:uk_user_dietary_preference,priority:2;index:idx_user_dietary_preference_type,priority:2" json:"preference_type"`
	PreferenceValue string    `gorm:"column:preference_value;type:varchar(100);not null" json:"preference_value"`
	NormalizedValue string    `gorm:"column:normalized_value;type:varchar(100);not null;uniqueIndex:uk_user_dietary_preference,priority:3" json:"normalized_value"`
	Note            string    `gorm:"column:note;type:varchar(255);not null;default:''" json:"note"`
	CreatedAt       time.Time `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt       time.Time `gorm:"column:updated_at;not null" json:"updated_at"`
}

// TableName 指定用户饮食偏好表名。
func (UserDietaryPreference) TableName() string { return "user_dietary_preference" }

const (
	// DietaryPreferenceTaste 表示口味偏好，例如清淡、微辣。
	DietaryPreferenceTaste int8 = 1
	// DietaryPreferenceCuisine 表示菜系偏好，例如家常菜、粤菜。
	DietaryPreferenceCuisine int8 = 2
	// DietaryPreferenceHabit 表示饮食习惯，例如少油、少盐。
	DietaryPreferenceHabit int8 = 3
	// DietaryPreferenceAvoid 表示主动忌口的食材。
	DietaryPreferenceAvoid int8 = 4
	// DietaryPreferenceAllergy 表示过敏食材，推荐时必须排除。
	DietaryPreferenceAllergy int8 = 5
)

// IsValidDietaryPreferenceType 判断偏好类型是否属于当前产品支持范围。
func IsValidDietaryPreferenceType(value int8) bool {
	return value >= DietaryPreferenceTaste && value <= DietaryPreferenceAllergy
}
