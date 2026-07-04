package handler

import (
	"context"
	"log"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	dishv1 "github.com/lijunsheng/familyos/proto/gen/dish/v1"
	"google.golang.org/grpc"
)

// DishHandler 菜谱 HTTP 处理器
type DishHandler struct {
	client dishv1.DishServiceClient
}

// NewDishHandler 创建 DishHandler
func NewDishHandler(conn *grpc.ClientConn) *DishHandler {
	return &DishHandler{
		client: dishv1.NewDishServiceClient(conn),
	}
}

// ListCategories GET /api/v1/dish/categories
func (h *DishHandler) ListCategories(c *gin.Context) {
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	resp, err := h.client.ListCategories(ctx, &dishv1.ListCategoriesRequest{})
	if err != nil {
		log.Printf("gRPC ListCategories 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	categories := make([]gin.H, 0, len(resp.GetCategories()))
	for _, cat := range resp.GetCategories() {
		categories = append(categories, gin.H{
			"id":   cat.GetId(),
			"name": cat.GetName(),
			"sort": cat.GetSort(),
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"code":       resp.GetCode(),
		"message":    resp.GetMessage(),
		"categories": categories,
	})
}

// ListDishesByCategory GET /api/v1/dish/dishes?category_id=1
func (h *DishHandler) ListDishesByCategory(c *gin.Context) {
	categoryIDStr := c.DefaultQuery("category_id", "0")
	categoryID, err := strconv.ParseInt(categoryIDStr, 10, 64)
	if err != nil || categoryID <= 0 {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供有效的 category_id",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	req := &dishv1.ListDishesByCategoryRequest{
		CategoryId: categoryID,
	}
	resp, err := h.client.ListDishesByCategory(ctx, req)
	if err != nil {
		log.Printf("gRPC ListDishesByCategory 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	dishes := make([]gin.H, 0, len(resp.GetDishes()))
	for _, d := range resp.GetDishes() {
		dishes = append(dishes, gin.H{
			"id":          d.GetId(),
			"category_id": d.GetCategoryId(),
			"name":        d.GetName(),
			"description": d.GetDescription(),
			"image_key":   d.GetImageKey(),
			"sort":        d.GetSort(),
			"created_at":  d.GetCreatedAt(),
			"updated_at":  d.GetUpdatedAt(),
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
		"dishes":  dishes,
	})
}

// SearchDishes GET /api/v1/dish/search?keyword=红烧
func (h *DishHandler) SearchDishes(c *gin.Context) {
	keyword := c.DefaultQuery("keyword", "")
	if keyword == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    1999,
			"message": "请提供搜索关键字",
		})
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	req := &dishv1.SearchDishesRequest{Keyword: keyword}
	resp, err := h.client.SearchDishes(ctx, req)
	if err != nil {
		log.Printf("gRPC SearchDishes 调用失败: %v", err)
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    1999,
			"message": "服务内部错误",
		})
		return
	}

	dishes := make([]gin.H, 0, len(resp.GetDishes()))
	for _, d := range resp.GetDishes() {
		dishes = append(dishes, gin.H{
			"id":          d.GetId(),
			"category_id": d.GetCategoryId(),
			"name":        d.GetName(),
			"description": d.GetDescription(),
			"image_key":   d.GetImageKey(),
			"sort":        d.GetSort(),
			"created_at":  d.GetCreatedAt(),
			"updated_at":  d.GetUpdatedAt(),
		})
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    resp.GetCode(),
		"message": resp.GetMessage(),
		"dishes":  dishes,
	})
}
