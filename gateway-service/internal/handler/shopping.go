package handler

import (
	"context"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/lijunsheng/familyos/gateway-service/internal/middleware"
	familyv1 "github.com/lijunsheng/familyos/proto/gen/family/v1"
)

// GenerateShoppingList POST /api/v1/family/shopping-lists/generate 根据家庭菜单生成购物清单。
func (h *FamilyHandler) GenerateShoppingList(c *gin.Context) {
	var body struct {
		FamilyID  int64  `json:"family_id"`
		StartDate string `json:"start_date"`
		EndDate   string `json:"end_date"`
		Name      string `json:"name"`
	}
	if err := c.ShouldBindJSON(&body); err != nil || body.FamilyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请求格式错误"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
	defer cancel()
	resp, err := h.client.GenerateShoppingList(ctx, &familyv1.GenerateShoppingListRequest{FamilyId: body.FamilyID, StartDate: body.StartDate, EndDate: body.EndDate, Name: body.Name, UserId: int64(middleware.CurrentUserID(c))})
	if err != nil {
		log.Printf("gRPC GenerateShoppingList 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	if resp.GetCode() != 0 {
		c.JSON(familyHTTPStatus(resp.GetCode()), shoppingListResponseJSON(resp))
		return
	}
	c.JSON(http.StatusCreated, shoppingListResponseJSON(resp))
}

// ListShoppingLists GET /api/v1/family/shopping-lists 查询家庭购物清单。
func (h *FamilyHandler) ListShoppingLists(c *gin.Context) {
	familyID, err := strconv.ParseInt(c.Query("family_id"), 10, 64)
	if err != nil || familyID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请提供有效的 family_id"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.ListShoppingLists(ctx, &familyv1.ListShoppingListsRequest{FamilyId: familyID, UserId: int64(middleware.CurrentUserID(c))})
	if err != nil {
		log.Printf("gRPC ListShoppingLists 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	lists := make([]gin.H, 0, len(resp.GetShoppingLists()))
	for _, list := range resp.GetShoppingLists() {
		lists = append(lists, shoppingListJSON(list))
	}
	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "shopping_lists": lists})
}

// GetShoppingList GET /api/v1/family/shopping-lists/:id 查询购物清单详情。
func (h *FamilyHandler) GetShoppingList(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请提供有效的购物清单ID"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.GetShoppingList(ctx, &familyv1.GetShoppingListRequest{Id: id, UserId: int64(middleware.CurrentUserID(c))})
	if err != nil {
		log.Printf("gRPC GetShoppingList 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	c.JSON(familyHTTPStatus(resp.GetCode()), shoppingListResponseJSON(resp))
}

// UpdateShoppingItemPurchased PATCH /api/v1/family/shopping-list-items/:id 更新购买状态。
func (h *FamilyHandler) UpdateShoppingItemPurchased(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请提供有效的购物项目ID"})
		return
	}
	var body struct {
		IsPurchased *bool `json:"is_purchased"`
	}
	if err := c.ShouldBindJSON(&body); err != nil || body.IsPurchased == nil {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "is_purchased 必须是布尔值"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.UpdateShoppingItemPurchased(ctx, &familyv1.UpdateShoppingItemPurchasedRequest{ItemId: id, UserId: int64(middleware.CurrentUserID(c)), IsPurchased: *body.IsPurchased})
	if err != nil {
		log.Printf("gRPC UpdateShoppingItemPurchased 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{"code": resp.GetCode(), "message": resp.GetMessage()})
}

// AddManualShoppingItem POST /api/v1/family/shopping-list-items 添加手动购物项目。
func (h *FamilyHandler) AddManualShoppingItem(c *gin.Context) {
	var body struct {
		ShoppingListID int64    `json:"shopping_list_id"`
		IngredientName string   `json:"ingredient_name"`
		Quantity       *float64 `json:"quantity"`
		QuantityText   string   `json:"quantity_text"`
		Unit           string   `json:"unit"`
	}
	if err := c.ShouldBindJSON(&body); err != nil || body.ShoppingListID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请求格式错误"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.AddManualShoppingItem(ctx, &familyv1.AddManualShoppingItemRequest{ShoppingListId: body.ShoppingListID, UserId: int64(middleware.CurrentUserID(c)), IngredientName: body.IngredientName, Quantity: body.Quantity, QuantityText: body.QuantityText, Unit: body.Unit})
	if err != nil {
		log.Printf("gRPC AddManualShoppingItem 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	response := gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "item": shoppingItemJSON(resp.GetItem())}
	if resp.GetCode() == 0 {
		c.JSON(http.StatusCreated, response)
		return
	}
	c.JSON(familyHTTPStatus(resp.GetCode()), response)
}

// DeleteShoppingItem DELETE /api/v1/family/shopping-list-items/:id 删除购物项目。
func (h *FamilyHandler) DeleteShoppingItem(c *gin.Context) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 1999, "message": "请提供有效的购物项目ID"})
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	resp, err := h.client.DeleteShoppingItem(ctx, &familyv1.DeleteShoppingItemRequest{ItemId: id, UserId: int64(middleware.CurrentUserID(c))})
	if err != nil {
		log.Printf("gRPC DeleteShoppingItem 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{"code": 1999, "message": "服务内部错误"})
		return
	}
	c.JSON(familyHTTPStatus(resp.GetCode()), gin.H{"code": resp.GetCode(), "message": resp.GetMessage()})
}

// shoppingListResponseJSON 将购物清单 gRPC 响应转换为 HTTP JSON。
func shoppingListResponseJSON(resp *familyv1.ShoppingListResponse) gin.H {
	items := make([]gin.H, 0, len(resp.GetItems()))
	for _, item := range resp.GetItems() {
		items = append(items, shoppingItemJSON(item))
	}
	return gin.H{"code": resp.GetCode(), "message": resp.GetMessage(), "shopping_list": shoppingListJSON(resp.GetShoppingList()), "items": items}
}

// shoppingListJSON 将购物清单信息转换为 HTTP JSON。
func shoppingListJSON(list *familyv1.ShoppingListInfo) gin.H {
	if list == nil {
		return nil
	}
	return gin.H{"id": list.GetId(), "family_id": list.GetFamilyId(), "created_by": list.GetCreatedBy(), "name": list.GetName(), "start_date": list.GetStartDate(), "end_date": list.GetEndDate(), "status": list.GetStatus(), "created_at": list.GetCreatedAt(), "updated_at": list.GetUpdatedAt()}
}

// shoppingItemJSON 将购物项目转换为 HTTP JSON。
func shoppingItemJSON(item *familyv1.ShoppingItemInfo) gin.H {
	if item == nil {
		return nil
	}
	var quantity any
	if item.Quantity != nil {
		quantity = item.GetQuantity()
	}
	return gin.H{"id": item.GetId(), "shopping_list_id": item.GetShoppingListId(), "ingredient_name": item.GetIngredientName(), "quantity": quantity, "quantity_text": item.GetQuantityText(), "unit": item.GetUnit(), "is_purchased": item.GetIsPurchased(), "source": item.GetSource(), "sort_order": item.GetSortOrder(), "created_at": item.GetCreatedAt(), "updated_at": item.GetUpdatedAt()}
}
