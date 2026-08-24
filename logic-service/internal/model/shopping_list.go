package model

import "time"

// ShoppingList 家庭购物清单模型。
type ShoppingList struct {
	ID        uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	FamilyID  uint64    `gorm:"column:family_id;not null;index:idx_shopping_list_family_status,priority:1;index:idx_shopping_list_family_dates,priority:1" json:"family_id"`
	CreatedBy uint64    `gorm:"column:created_by;not null;index" json:"created_by"`
	Name      string    `gorm:"column:name;type:varchar(100);not null" json:"name"`
	StartDate time.Time `gorm:"column:start_date;type:date;not null;index:idx_shopping_list_family_dates,priority:2" json:"start_date"`
	EndDate   time.Time `gorm:"column:end_date;type:date;not null;index:idx_shopping_list_family_dates,priority:3" json:"end_date"`
	Status    int8      `gorm:"column:status;type:tinyint;not null;default:1;index:idx_shopping_list_family_status,priority:2" json:"status"`
	CreatedAt time.Time `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt time.Time `gorm:"column:updated_at;not null" json:"updated_at"`
}

// TableName 指定购物清单表名。
func (ShoppingList) TableName() string { return "shopping_list" }

// ShoppingListItem 购物清单项目模型。
type ShoppingListItem struct {
	ID                uint64    `gorm:"column:id;primaryKey;autoIncrement" json:"id"`
	ShoppingListID    uint64    `gorm:"column:shopping_list_id;not null;index:idx_shopping_item_list_purchased,priority:1" json:"shopping_list_id"`
	IngredientName    string    `gorm:"column:ingredient_name;type:varchar(100);not null" json:"ingredient_name"`
	Quantity          *float64  `gorm:"column:quantity;type:decimal(10,2)" json:"quantity"`
	QuantityText      string    `gorm:"column:quantity_text;type:varchar(50);not null;default:''" json:"quantity_text"`
	Unit              string    `gorm:"column:unit;type:varchar(20);not null;default:''" json:"unit"`
	PurchasedQuantity float64   `gorm:"column:purchased_quantity;type:decimal(10,2);not null;default:0" json:"purchased_quantity"`
	IsPurchased       int8      `gorm:"column:is_purchased;type:tinyint;not null;default:0;index:idx_shopping_item_list_purchased,priority:2" json:"is_purchased"`
	Source            string    `gorm:"column:source;type:varchar(20);not null;default:'manual'" json:"source"`
	SortOrder         int       `gorm:"column:sort_order;type:int;not null;default:0;index:idx_shopping_item_list_purchased,priority:3" json:"sort_order"`
	CreatedAt         time.Time `gorm:"column:created_at;not null" json:"created_at"`
	UpdatedAt         time.Time `gorm:"column:updated_at;not null" json:"updated_at"`
}

// TableName 指定购物清单项目表名。
func (ShoppingListItem) TableName() string { return "shopping_list_item" }

const (
	// ShoppingListStatusActive 表示清单仍在使用。
	ShoppingListStatusActive int8 = 1
	// ShoppingListStatusArchived 表示清单已归档。
	ShoppingListStatusArchived int8 = 2
	// ShoppingItemUnpurchased 表示项目尚未购买。
	ShoppingItemUnpurchased int8 = 0
	// ShoppingItemPurchased 表示项目已购买。
	ShoppingItemPurchased int8 = 1
)
