package repository

import (
	"context"
	"errors"
	"time"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"gorm.io/gorm"
)

// ShoppingListRepo 负责购物清单及项目的数据访问。
type ShoppingListRepo struct {
	db *gorm.DB
}

// NewShoppingListRepo 创建购物清单 Repository。
func NewShoppingListRepo(db *gorm.DB) *ShoppingListRepo { return &ShoppingListRepo{db: db} }

// CreateWithItems 在一个事务中创建清单及其项目，避免出现只有清单没有项目的半成品数据。
func (r *ShoppingListRepo) CreateWithItems(ctx context.Context, list *model.ShoppingList, items []model.ShoppingListItem) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(list).Error; err != nil {
			return err
		}
		for index := range items {
			items[index].ShoppingListID = list.ID
		}
		if len(items) > 0 {
			if err := tx.Create(&items).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// FindByFamilyDates 查询家庭指定日期范围的现有清单。
func (r *ShoppingListRepo) FindByFamilyDates(ctx context.Context, familyID uint64, startDate, endDate time.Time) (*model.ShoppingList, error) {
	var list model.ShoppingList
	err := r.db.WithContext(ctx).Where("family_id = ? AND start_date = ? AND end_date = ?", familyID, startDate, endDate).Order("id DESC").First(&list).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}
	return &list, err
}

// ReplaceItems 在事务中替换指定清单的项目，确保生成过程不会留下半成品。
func (r *ShoppingListRepo) ReplaceItems(ctx context.Context, list *model.ShoppingList, items []model.ShoppingListItem) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("shopping_list_id = ?", list.ID).Delete(&model.ShoppingListItem{}).Error; err != nil {
			return err
		}
		for index := range items {
			items[index].ShoppingListID = list.ID
		}
		if len(items) > 0 {
			if err := tx.Create(&items).Error; err != nil {
				return err
			}
		}
		return tx.Model(list).Updates(map[string]interface{}{"name": list.Name, "updated_at": time.Now()}).Error
	})
}

// ListByFamily 查询家庭的购物清单，按最近更新时间倒序排列。
func (r *ShoppingListRepo) ListByFamily(ctx context.Context, familyID uint64) ([]model.ShoppingList, error) {
	var lists []model.ShoppingList
	err := r.db.WithContext(ctx).Where("family_id = ?", familyID).Order("updated_at DESC, id DESC").Find(&lists).Error
	return lists, err
}

// GetWithItems 查询指定购物清单及其项目。
func (r *ShoppingListRepo) GetWithItems(ctx context.Context, id uint64) (*model.ShoppingList, []model.ShoppingListItem, error) {
	var list model.ShoppingList
	if err := r.db.WithContext(ctx).First(&list, id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil, nil
		}
		return nil, nil, err
	}
	var items []model.ShoppingListItem
	if err := r.db.WithContext(ctx).Where("shopping_list_id = ?", id).Order("is_purchased ASC, sort_order ASC, id ASC").Find(&items).Error; err != nil {
		return nil, nil, err
	}
	return &list, items, nil
}

// UpdateItemPurchased 更新项目的已购买数量及完成状态。
func (r *ShoppingListRepo) UpdateItemPurchased(ctx context.Context, itemID uint64, purchasedQuantity float64, purchased bool) error {
	updates := map[string]interface{}{"purchased_quantity": purchasedQuantity, "is_purchased": model.ShoppingItemUnpurchased}
	if purchased {
		updates["is_purchased"] = model.ShoppingItemPurchased
	}
	result := r.db.WithContext(ctx).Model(&model.ShoppingListItem{}).Where("id = ?", itemID).Updates(updates)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return gorm.ErrRecordNotFound
	}
	return nil
}

// CreateManualItem 添加手动购物项目。
func (r *ShoppingListRepo) CreateManualItem(ctx context.Context, item *model.ShoppingListItem) error {
	return r.db.WithContext(ctx).Create(item).Error
}

// DeleteItem 删除购物项目。
func (r *ShoppingListRepo) DeleteItem(ctx context.Context, itemID uint64) error {
	result := r.db.WithContext(ctx).Delete(&model.ShoppingListItem{}, itemID)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return gorm.ErrRecordNotFound
	}
	return nil
}

// GetItemOwner 查询项目所属清单和家庭，用于权限校验。
func (r *ShoppingListRepo) GetItemOwner(ctx context.Context, itemID uint64) (uint64, uint64, error) {
	var result struct {
		ShoppingListID uint64
		FamilyID       uint64
	}
	err := r.db.WithContext(ctx).Table("shopping_list_item AS i").Select("i.shopping_list_id, l.family_id").Joins("JOIN shopping_list AS l ON l.id = i.shopping_list_id").Where("i.id = ?", itemID).Scan(&result).Error
	if err != nil {
		return 0, 0, err
	}
	if result.ShoppingListID == 0 {
		return 0, 0, gorm.ErrRecordNotFound
	}
	return result.ShoppingListID, result.FamilyID, nil
}

// ParseShoppingDate 将接口日期解析为数据库日期，统一清除时分秒。
func ParseShoppingDate(value string) (time.Time, error) { return time.Parse("2006-01-02", value) }
