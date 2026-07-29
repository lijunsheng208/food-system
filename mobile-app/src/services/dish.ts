import api from './api';
import { OSS_PUBLIC_BASE_URL } from '../config';

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

export interface IngredientInfo {
  id: number;
  name: string;
  amount: number | null;
  amount_text: string;
  unit: string;
  sort: number;
}

export interface IngredientGroup {
  name: string;
  ingredients: IngredientInfo[];
}

export interface DishStepInfo {
  id: number;
  step_no: number;
  description: string;
  image_key: string;
  image_keys?: string[];
  timer_seconds?: number;
}

export interface DishDetailInfo {
  id: number;
  category_id: number;
  name: string;
  description: string;
  image_key: string;
  cook_minutes: number;
  difficulty: number;
  servings: number;
  tips: string;
  ingredient_groups: IngredientGroup[];
  steps: DishStepInfo[];
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

interface DishDetailResponse {
  code: number;
  message: string;
  dish: DishDetailInfo;
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

/**
 * 查询菜谱详情
 */
export async function fetchDishDetail(dishId: number): Promise<DishDetailInfo> {
  const { data } = await api.get<DishDetailResponse>(`/dish/${dishId}`);
  if (data.code !== 0 || !data.dish) {
    throw new Error(data.message || '查询菜谱详情失败');
  }
  return {
    ...data.dish,
    ingredient_groups: data.dish.ingredient_groups ?? [],
    steps: data.dish.steps ?? [],
  };
}

/**
 * 将 OSS key 转成可访问的公网 URL；完整 URL 原样返回。
 */
export function resolveDishImageUrl(imageKey: string): string | null {
  const key = imageKey.trim();
  if (!key) return null;
  if (/^https?:\/\//i.test(key)) return key;
  return `${OSS_PUBLIC_BASE_URL}/${key.replace(/^\/+/, '')}`;
}

/**
 * 兼容当前单图 image_key 和后续多图 image_keys。
 */
export function resolveStepImageUrls(step: DishStepInfo): string[] {
  const keys = step.image_keys?.length
    ? step.image_keys
    : step.image_key
      ? [step.image_key]
      : [];

  return Array.from(
    new Set(
      keys
        .map(resolveDishImageUrl)
        .filter((url): url is string => Boolean(url)),
    ),
  );
}
