package model

import "time"

// FamilyMember 家庭成员表模型
type FamilyMember struct {
	ID          uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	FamilyID    uint64    `gorm:"column:family_id;not null;uniqueIndex:uk_family_user;index:idx_family_role" json:"family_id"`
	UserID      uint64    `gorm:"column:user_id;not null;uniqueIndex:uk_family_user;uniqueIndex:uk_user_current_family" json:"user_id"`
	Role        int8      `gorm:"column:role;not null;default:3;index:idx_family_role" json:"role"`
	Relation    *string   `gorm:"column:relation;type:varchar(20)" json:"relation"`
	DisplayName *string   `gorm:"column:display_name;type:varchar(50)" json:"display_name"`
	JoinedAt    time.Time `gorm:"column:joined_at;not null" json:"joined_at"`
	CreatedAt   time.Time `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt   time.Time `gorm:"column:updated_at;not null" json:"updated_at"`
}

func (FamilyMember) TableName() string {
	return "family_members"
}

const (
	FamilyRoleOwner  int8 = 1
	FamilyRoleAdmin  int8 = 2
	FamilyRoleMember int8 = 3
)

// FamilyMemberWithUser 联表查询结果
type FamilyMemberWithUser struct {
	UserID      uint64     `json:"user_id"`
	Phone       string     `json:"phone"`
	Nickname    string     `json:"nickname"`
	Avatar      *string    `json:"avatar"`
	Role        int8       `json:"role"`
	Relation    *string    `json:"relation"`
	DisplayName *string    `json:"display_name"`
	JoinedAt    time.Time  `json:"joined_at"`
}
