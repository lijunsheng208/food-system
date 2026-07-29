package model

import "time"

// Family 家庭表模型
type Family struct {
	ID                  uint64     `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	Name                string     `gorm:"column:name;type:varchar(50);not null" json:"name"`
	Avatar              *string    `gorm:"column:avatar;type:varchar(500)" json:"avatar"`
	Description         *string    `gorm:"column:description;type:varchar(255)" json:"description"`
	OwnerUserID         uint64     `gorm:"column:owner_user_id;not null;index:idx_owner_user_id" json:"owner_user_id"`
	InviteCode          string     `gorm:"column:invite_code;type:varchar(20);not null;uniqueIndex:uk_invite_code" json:"invite_code"`
	InviteCodeExpiredAt *time.Time `gorm:"column:invite_code_expired_at" json:"invite_code_expired_at"`
	MemberCount         uint       `gorm:"column:member_count;not null;default:1" json:"member_count"`
	MaxMemberCount      uint       `gorm:"column:max_member_count;not null;default:20" json:"max_member_count"`
	Status              int8       `gorm:"column:status;not null;default:1" json:"status"`
	CreatedAt           time.Time  `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt           time.Time  `gorm:"column:updated_at;not null" json:"updated_at"`
}

func (Family) TableName() string {
	return "families"
}

const (
	FamilyStatusNormal   int8 = 1
	FamilyStatusDissolve int8 = 2
)
