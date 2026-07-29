package repository

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

// FamilyRepo 家庭数据访问
type FamilyRepo struct {
	db *gorm.DB
}

// NewFamilyRepo 创建 FamilyRepo
func NewFamilyRepo(db *gorm.DB) *FamilyRepo {
	return &FamilyRepo{db: db}
}

// ─── 家庭 CRUD ────────────────────────────────────────────────

// GetFamilyByID 按 ID 查询家庭
func (r *FamilyRepo) GetFamilyByID(ctx context.Context, familyID uint64) (*model.Family, error) {
	var family model.Family
	err := r.db.WithContext(ctx).Where("id = ?", familyID).First(&family).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &family, nil
}

// GetFamilyByInviteCode 按邀请码查询家庭
func (r *FamilyRepo) GetFamilyByInviteCode(ctx context.Context, code string) (*model.Family, error) {
	var family model.Family
	err := r.db.WithContext(ctx).
		Where("invite_code = ? AND status = ?", code, model.FamilyStatusNormal).
		First(&family).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &family, nil
}

// UpdateFamily 修改家庭信息（使用原生 SQL，支持 NULL 清空）
func (r *FamilyRepo) UpdateFamily(ctx context.Context, familyID uint64, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return nil
	}

	setParts := make([]string, 0, len(updates))
	args := make([]interface{}, 0, len(updates)+1)
	for col, val := range updates {
		setParts = append(setParts, fmt.Sprintf("`%s` = ?", col))
		args = append(args, val)
	}
	args = append(args, familyID)

	sql := fmt.Sprintf(
		"UPDATE `families` SET %s WHERE `id` = ?",
		strings.Join(setParts, ", "),
	)

	result := r.db.WithContext(ctx).Exec(sql, args...)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return gorm.ErrRecordNotFound
	}
	return nil
}

// DeleteAllMembers 删除家庭下所有成员（事务中使用）
func (r *FamilyRepo) DeleteAllMembers(ctx context.Context, tx *gorm.DB, familyID uint64) error {
	return tx.WithContext(ctx).
		Where("family_id = ?", familyID).
		Delete(&model.FamilyMember{}).Error
}

// ─── 事务：创建家庭 + 所有者 ─────────────────────────────────

// CreateFamilyWithOwner 事务创建家庭和所有者成员
func (r *FamilyRepo) CreateFamilyWithOwner(ctx context.Context, family *model.Family, member *model.FamilyMember) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(family).Error; err != nil {
			return err
		}
		member.FamilyID = family.ID
		if err := tx.Create(member).Error; err != nil {
			return err
		}
		return nil
	})
}

// ─── 事务：加入家庭 ───────────────────────────────────────────

// JoinFamily 事务插入成员并增加 member_count
func (r *FamilyRepo) JoinFamily(ctx context.Context, familyID uint64, member *model.FamilyMember) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		// 锁住家庭行防止并发超限
		var family model.Family
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
			Where("id = ?", familyID).First(&family).Error; err != nil {
			return err
		}
		if family.MemberCount >= family.MaxMemberCount {
			return errors.New("家庭成员数量已满")
		}
		if err := tx.Create(member).Error; err != nil {
			return err
		}
		if err := tx.Model(&family).Update("member_count", family.MemberCount+1).Error; err != nil {
			return err
		}
		return nil
	})
}

// ─── 事务：退出家庭 ───────────────────────────────────────────

// LeaveFamily 事务删除成员并减少 member_count
func (r *FamilyRepo) LeaveFamily(ctx context.Context, familyID, userID uint64) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		res := tx.Where("family_id = ? AND user_id = ?", familyID, userID).
			Delete(&model.FamilyMember{})
		if res.Error != nil {
			return res.Error
		}
		if res.RowsAffected == 0 {
			return gorm.ErrRecordNotFound
		}
		return tx.Model(&model.Family{}).
			Where("id = ?", familyID).
			Update("member_count", gorm.Expr("member_count - 1")).Error
	})
}

// ─── 事务：解散家庭 ───────────────────────────────────────────

// DissolveFamily 事务更新家庭状态并删除所有成员
func (r *FamilyRepo) DissolveFamily(ctx context.Context, familyID uint64) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Model(&model.Family{}).
			Where("id = ?", familyID).
			Updates(map[string]interface{}{
				"status":       model.FamilyStatusDissolve,
				"member_count": 0,
			}).Error; err != nil {
			return err
		}
		if err := tx.Where("family_id = ?", familyID).
			Delete(&model.FamilyMember{}).Error; err != nil {
			return err
		}
		return nil
	})
}

// ─── 事务：移除成员 ───────────────────────────────────────────

// RemoveMember 事务移除成员并维护 member_count
func (r *FamilyRepo) RemoveMember(ctx context.Context, familyID, userID uint64) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		res := tx.Where("family_id = ? AND user_id = ?", familyID, userID).
			Delete(&model.FamilyMember{})
		if res.Error != nil {
			return res.Error
		}
		if res.RowsAffected == 0 {
			return gorm.ErrRecordNotFound
		}
		return tx.Model(&model.Family{}).
			Where("id = ?", familyID).
			Update("member_count", gorm.Expr("member_count - 1")).Error
	})
}

// ─── 成员查询 ─────────────────────────────────────────────────

// GetMemberByUserID 查询用户当前家庭成员关系
func (r *FamilyRepo) GetMemberByUserID(ctx context.Context, userID uint64) (*model.FamilyMember, error) {
	var member model.FamilyMember
	err := r.db.WithContext(ctx).
		Where("user_id = ?", userID).
		First(&member).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &member, nil
}

// GetMember 查询指定家庭成员关系
func (r *FamilyRepo) GetMember(ctx context.Context, familyID, userID uint64) (*model.FamilyMember, error) {
	var member model.FamilyMember
	err := r.db.WithContext(ctx).
		Where("family_id = ? AND user_id = ?", familyID, userID).
		First(&member).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &member, nil
}

// ListMembers 联表查询成员与用户信息
func (r *FamilyRepo) ListMembers(ctx context.Context, familyID uint64) ([]model.FamilyMemberWithUser, error) {
	var results []model.FamilyMemberWithUser
	err := r.db.WithContext(ctx).
		Table("family_members fm").
		Select("u.id AS user_id, u.phone, u.nickname, u.avatar, fm.role, fm.relation, fm.display_name, fm.joined_at").
		Joins("JOIN users u ON u.id = fm.user_id").
		Where("fm.family_id = ?", familyID).
		Order("fm.role ASC, fm.joined_at ASC").
		Find(&results).Error
	return results, err
}

// ─── 成员修改 ─────────────────────────────────────────────────

// UpdateMember 修改成员角色/备注（使用原生 SQL 避免 GORM Updates(map) 静默失败）
func (r *FamilyRepo) UpdateMember(ctx context.Context, familyID, userID uint64, updates map[string]interface{}) error {
	if len(updates) == 0 {
		return nil
	}

	// 构建 SET 子句
	setParts := make([]string, 0, len(updates))
	args := make([]interface{}, 0, len(updates)+2)
	for col, val := range updates {
		setParts = append(setParts, fmt.Sprintf("`%s` = ?", col))
		args = append(args, val)
	}
	args = append(args, familyID, userID)

	sql := fmt.Sprintf(
		"UPDATE `family_members` SET %s WHERE `family_id` = ? AND `user_id` = ?",
		strings.Join(setParts, ", "),
	)

	result := r.db.WithContext(ctx).Exec(sql, args...)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return gorm.ErrRecordNotFound
	}
	return nil
}

// ─── 邀请码 ───────────────────────────────────────────────────

// ResetInviteCode 重置邀请码
func (r *FamilyRepo) ResetInviteCode(ctx context.Context, familyID uint64, code string, expiredAt *time.Time) error {
	updates := map[string]interface{}{
		"invite_code": code,
	}
	if expiredAt != nil {
		updates["invite_code_expired_at"] = expiredAt
	} else {
		updates["invite_code_expired_at"] = nil
	}
	return r.db.WithContext(ctx).
		Model(&model.Family{}).
		Where("id = ?", familyID).
		Updates(updates).Error
}
