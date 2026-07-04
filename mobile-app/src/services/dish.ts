import api from './api';

export interface CategoryInfo {
  id: number;
  name: string;
  sort: number;
}

export interface DishInfo {
  id: number;
  category_id: number;
  name: string;
  description: string;
  image_key: string;
  sort: number;
  created_at: string;
  updated_at: string;
}

interface ListCategoriesResponse {
  code: number;
  message: string;
  categories: CategoryInfo[];
}

interface ListDishesResponse {
  code: number;
  message: string;
  dishes: DishInfo[];
}

/**
 * 查询所有分类
 */
export async function fetchCategories(): Promise<CategoryInfo[]> {
  const { data } = await api.get<ListCategoriesResponse>('/dish/categories');
  if (data.code !== 0) {
    throw new Error(data.message || '查询分类失败');
  }
  return data.categories ?? [];
}

/**
 * 查询某分类下的菜谱
 */
export async function fetchDishesByCategory(
  categoryId: number,
): Promise<DishInfo[]> {
  const { data } = await api.get<ListDishesResponse>('/dish/dishes', {
    params: { category_id: categoryId },
  });
  if (data.code !== 0) {
    throw new Error(data.message || '查询菜谱失败');
  }
  return data.dishes ?? [];
}

/**
 * 搜索菜谱
 */
export async function searchDishes(keyword: string): Promise<DishInfo[]> {
  const { data } = await api.get<ListDishesResponse>('/dish/search', {
    params: { keyword },
  });
  if (data.code !== 0) {
    throw new Error(data.message || '搜索失败');
  }
  return data.dishes ?? [];
}
