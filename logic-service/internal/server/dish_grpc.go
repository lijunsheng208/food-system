package server

import (
	"context"
	"errors"

	"github.com/lijunsheng/familyos/logic-service/internal/model"
	"github.com/lijunsheng/familyos/logic-service/internal/service"
	dishv1 "github.com/lijunsheng/familyos/proto/gen/dish/v1"
)

const DishCodeNotFound = 2002

// DishServer gRPC DishService 实现
type DishServer struct {
	dishv1.UnimplementedDishServiceServer
	svc *service.DishService
}

// NewDishServer 创建 DishServer
func NewDishServer(svc *service.DishService) *DishServer {
	return &DishServer{svc: svc}
}

// ListCategories 实现分类列表查询接口
func (s *DishServer) ListCategories(ctx context.Context, req *dishv1.ListCategoriesRequest) (*dishv1.ListCategoriesResponse, error) {
	categories, err := s.svc.ListCategories(ctx)
	if err != nil {
		return &dishv1.ListCategoriesResponse{
			Code:    CodeInternalError,
			Message: "查询分类失败",
		}, nil
	}

	categoryInfos := make([]*dishv1.CategoryInfo, 0, len(categories))
	for _, c := range categories {
		categoryInfos = append(categoryInfos, toCategoryInfo(&c))
	}

	return &dishv1.ListCategoriesResponse{
		Code:       CodeSuccess,
		Message:    "查询成功",
		Categories: categoryInfos,
	}, nil
}

// ListDishesByCategory 实现分类下菜谱查询接口
func (s *DishServer) ListDishesByCategory(ctx context.Context, req *dishv1.ListDishesByCategoryRequest) (*dishv1.ListDishesByCategoryResponse, error) {
	dishes, err := s.svc.ListDishesByCategory(ctx, uint64(req.CategoryId))
	if err != nil {
		return &dishv1.ListDishesByCategoryResponse{
			Code:    CodeInternalError,
			Message: "查询菜谱失败",
		}, nil
	}

	dishInfos := make([]*dishv1.DishInfo, 0, len(dishes))
	for _, d := range dishes {
		dishInfos = append(dishInfos, toDishInfo(&d))
	}

	return &dishv1.ListDishesByCategoryResponse{
		Code:    CodeSuccess,
		Message: "查询成功",
		Dishes:  dishInfos,
	}, nil
}

// SearchDishes 实现搜索菜谱接口
func (s *DishServer) SearchDishes(ctx context.Context, req *dishv1.SearchDishesRequest) (*dishv1.SearchDishesResponse, error) {
	dishes, err := s.svc.SearchDishes(ctx, req.Keyword)
	if err != nil {
		return &dishv1.SearchDishesResponse{
			Code:    CodeInternalError,
			Message: "搜索菜谱失败",
		}, nil
	}

	dishInfos := make([]*dishv1.DishInfo, 0, len(dishes))
	for _, d := range dishes {
		dishInfos = append(dishInfos, toDishInfo(&d))
	}

	return &dishv1.SearchDishesResponse{
		Code:    CodeSuccess,
		Message: "搜索成功",
		Dishes:  dishInfos,
	}, nil
}

// GetDishDetail 实现菜谱详情查询接口
func (s *DishServer) GetDishDetail(ctx context.Context, req *dishv1.GetDishDetailRequest) (*dishv1.GetDishDetailResponse, error) {
	detail, err := s.svc.GetDishDetail(ctx, uint64(req.DishId))
	if err != nil {
		if errors.Is(err, service.ErrDishNotFound) {
			return &dishv1.GetDishDetailResponse{
				Code:    DishCodeNotFound,
				Message: err.Error(),
			}, nil
		}
		return &dishv1.GetDishDetailResponse{
			Code:    CodeInternalError,
			Message: "查询菜谱详情失败",
		}, nil
	}

	return &dishv1.GetDishDetailResponse{
		Code:    CodeSuccess,
		Message: "查询成功",
		Dish:    toDishDetailInfo(detail),
	}, nil
}

// toCategoryInfo 将 model.DishCategory 转为 proto CategoryInfo
func toCategoryInfo(c *model.DishCategory) *dishv1.CategoryInfo {
	return &dishv1.CategoryInfo{
		Id:   int64(c.ID),
		Name: c.Name,
		Sort: int32(c.Sort),
	}
}

// toDishInfo 将 model.Dish 转为 proto DishInfo
func toDishInfo(d *model.Dish) *dishv1.DishInfo {
	info := &dishv1.DishInfo{
		Id:         int64(d.ID),
		CategoryId: int64(d.CategoryID),
		Name:       d.Name,
		ImageKey:   d.ImageKey,
		Sort:       int32(d.Sort),
		CreatedAt:  d.CreatedAt.Format("2006-01-02 15:04:05"),
		UpdatedAt:  d.UpdatedAt.Format("2006-01-02 15:04:05"),
	}
	if d.Description != nil {
		info.Description = *d.Description
	}
	return info
}

func toDishDetailInfo(detail *service.DishDetail) *dishv1.DishDetailInfo {
	dish := detail.Dish
	info := &dishv1.DishDetailInfo{
		Id:               int64(dish.ID),
		CategoryId:       int64(dish.CategoryID),
		Name:             dish.Name,
		ImageKey:         dish.ImageKey,
		CookMinutes:      int32(dish.CookMinutes),
		Difficulty:       int32(dish.Difficulty),
		Servings:         int32(dish.Servings),
		IngredientGroups: make([]*dishv1.IngredientGroup, 0, len(detail.IngredientGroups)),
		Steps:            make([]*dishv1.DishStepInfo, 0, len(detail.Steps)),
	}
	if dish.Description != nil {
		info.Description = *dish.Description
	}
	if dish.Tips != nil {
		info.Tips = *dish.Tips
	}

	for _, group := range detail.IngredientGroups {
		groupInfo := &dishv1.IngredientGroup{
			Name:        group.Name,
			Ingredients: make([]*dishv1.IngredientInfo, 0, len(group.Ingredients)),
		}
		for _, ingredient := range group.Ingredients {
			groupInfo.Ingredients = append(groupInfo.Ingredients, &dishv1.IngredientInfo{
				Id:         int64(ingredient.ID),
				Name:       ingredient.Name,
				Amount:     ingredient.Amount,
				AmountText: ingredient.AmountText,
				Unit:       ingredient.Unit,
				Sort:       int32(ingredient.Sort),
			})
		}
		info.IngredientGroups = append(info.IngredientGroups, groupInfo)
	}

	for _, step := range detail.Steps {
		info.Steps = append(info.Steps, &dishv1.DishStepInfo{
			Id:          int64(step.ID),
			StepNo:      int32(step.StepNo),
			Description: step.Description,
			ImageKey:    step.ImageKey,
		})
	}

	return info
}
