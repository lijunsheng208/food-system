/**
 * 家庭模块 API 服务
 *
 * 所有接口对接 gateway-service /api/v1/family/*
 * 当前操作者由 Gateway 从 Access Token 解析，请求中的身份 ID 不会发送。
 */

import api from './api';
import type {
  FamilyInfo,
  FamilyMemberInfo,
  ApiResponse,
  FamilyMealPlanInfo,
  MealType,
  ShoppingItemInfo,
  ShoppingListInfo,
  FamilyMealPlanRating,
} from '../types/family';
import type { FamilyDietaryProfile, FamilyDietaryProfileInput } from '../types/familyDietary';

// getFamilyDietaryProfile 查询当前家庭的预算和饮食说明。
export async function getFamilyDietaryProfile(familyId: number): Promise<FamilyDietaryProfile | null> {
  const { data } = await api.get<{ code: number; message: string; profile: FamilyDietaryProfile | null }>(`/family/${familyId}/dietary-profile`);
  if (data.code !== 0) throw new Error(data.message || '查询家庭饮食设置失败');
  return data.profile;
}

// saveFamilyDietaryProfile 保存当前家庭的预算和饮食说明。
export async function saveFamilyDietaryProfile(familyId: number, input: FamilyDietaryProfileInput): Promise<FamilyDietaryProfile> {
  const { data } = await api.put<{ code: number; message: string; profile: FamilyDietaryProfile }>(`/family/${familyId}/dietary-profile`, input);
  if (data.code !== 0) throw new Error(data.message || '保存家庭饮食设置失败');
  return data.profile;
}

// ─── 查询我的家庭 ────────────────────────────────────────────

export async function getMyFamily() {
  const { data } = await api.get<{
    code: number;
    message: string;
    family: FamilyInfo | null;
  }>('/family/my');
  if (data.code !== 0) throw new Error(data.message || '查询家庭失败');
  return data.family;
}

// ─── 创建家庭 ──────────────────────────────────────────────────

export async function createFamily(params: {
  name: string;
  avatar?: string;
  description?: string;
}) {
  const { data } = await api.post<
    ApiResponse & { family_id: number; invite_code: string }
  >('/family/create', params);
  if (data.code !== 0) throw new Error(data.message || '创建家庭失败');
  return data;
}

// ─── 修改家庭信息 ──────────────────────────────────────────────

export async function updateFamily(params: {
  family_id: number;
  name?: string;
  avatar?: string;
  description?: string;
}) {
  const { family_id, ...body } = params;
  const { data } = await api.put<ApiResponse>(
    `/family/${family_id}`,
    body,
  );
  if (data.code !== 0) throw new Error(data.message || '更新家庭失败');
  return data;
}

// ─── 通过邀请码加入家庭 ────────────────────────────────────────

export async function joinFamily(params: {
  invite_code: string;
  relation?: string;
  display_name?: string;
}) {
  const { data } = await api.post<
    ApiResponse & { family_id: number }
  >('/family/join', params);
  if (data.code !== 0) throw new Error(data.message || '加入家庭失败');
  return data;
}

// ─── 退出家庭 ──────────────────────────────────────────────────

export async function leaveFamily() {
  const { data } = await api.post<ApiResponse>('/family/leave', {});
  if (data.code !== 0) throw new Error(data.message || '退出家庭失败');
  return data;
}

// ─── 解散家庭 ──────────────────────────────────────────────────

export async function dissolveFamily(familyId: number) {
  const { data } = await api.delete<ApiResponse>(`/family/${familyId}`);
  if (data.code !== 0) throw new Error(data.message || '解散家庭失败');
  return data;
}

// ─── 查询家庭成员列表 ──────────────────────────────────────────

export async function listFamilyMembers(familyId: number) {
  const { data } = await api.get<{
    code: number;
    message: string;
    members: FamilyMemberInfo[];
  }>(`/family/${familyId}/members`);
  if (data.code !== 0) throw new Error(data.message || '查询成员失败');
  return data.members;
}

// ─── 修改成员信息 ──────────────────────────────────────────────

export async function updateMember(params: {
  family_id: number;
  member_user_id: number;
  role?: number;
  relation?: string;
  display_name?: string;
}) {
  const { family_id, member_user_id, ...body } = params;
  const { data } = await api.put<ApiResponse>(
    `/family/${family_id}/members/${member_user_id}`,
    body,
  );
  if (data.code !== 0) throw new Error(data.message || '更新成员失败');
  return data;
}

// ─── 移除成员 ──────────────────────────────────────────────────

export async function removeMember(familyId: number, memberUserId: number) {
  const { data } = await api.delete<ApiResponse>(
    `/family/${familyId}/members/${memberUserId}`,
    {},
  );
  if (data.code !== 0) throw new Error(data.message || '移除成员失败');
  return data;
}

// ─── 重置邀请码 ────────────────────────────────────────────────

export async function resetInviteCode(familyId: number, expireHours?: number) {
  const { data } = await api.post<ApiResponse & {
    invite_code: string;
    invite_code_expired_at: string;
  }>(`/family/${familyId}/invite-code/reset`, {
    expire_hours: expireHours,
  });
  if (data.code !== 0) throw new Error(data.message || '重置邀请码失败');
  return data;
}

export async function createMealPlan(params: {
  family_id: number;
  dish_id: number;
  meal_date: string;
  meal_type: MealType;
  servings: number;
  cook_user_id?: number;
}) {
  const { data } = await api.post<ApiResponse & { meal_plan: FamilyMealPlanInfo }>(
    '/family/meal-plans', params,
  );
  if (data.code !== 0) throw new Error(data.message || '加入家庭菜单失败');
  return data.meal_plan;
}

export async function listMealPlans(
  familyId: number,
  startDate: string,
  endDate: string,
) {
  const { data } = await api.get<ApiResponse & { meal_plans: FamilyMealPlanInfo[] }>(
    `/family/${familyId}/meal-plans`,
    { params: { start_date: startDate, end_date: endDate } },
  );
  if (data.code !== 0) throw new Error(data.message || '查询家庭菜单失败');
  return data.meal_plans ?? [];
}

export async function updateMealPlan(
  id: number,
  params: {
    meal_date?: string;
    meal_type?: MealType;
    servings?: number;
    cook_user_id?: number;
    status?: 0 | 1 | 2 | 3;
  },
) {
  const { data } = await api.patch<ApiResponse & { meal_plan: FamilyMealPlanInfo }>(
    `/family/meal-plans/${id}`, params,
  );
  if (data.code !== 0) throw new Error(data.message || '修改家庭菜单失败');
  return data.meal_plan;
}

// upsertMealPlanRating 保存或更新当前用户对已完成家庭菜单的评分和文字评价。
export async function upsertMealPlanRating(mealPlanId: number, rating: number, comment = '') {
  const { data } = await api.post<ApiResponse & { rating: FamilyMealPlanRating }>(
    `/family/meal-plans/${mealPlanId}/rating`, { rating, comment },
  );
  if (data.code !== 0) throw new Error(data.message || '保存评价失败');
  return data.rating;
}

// listMealPlanRatings 查询某次家庭菜单的成员评价和平均分。
export async function listMealPlanRatings(mealPlanId: number) {
  const { data } = await api.get<ApiResponse & {
    ratings: FamilyMealPlanRating[];
    average_rating: number;
    rating_count: number;
    my_rating: number | null;
    my_comment: string;
  }>(`/family/meal-plans/${mealPlanId}/ratings`);
  if (data.code !== 0) throw new Error(data.message || '查询评价失败');
  return data;
}

export async function deleteMealPlan(id: number) {
  const { data } = await api.delete<ApiResponse>(`/family/meal-plans/${id}`);
  if (data.code !== 0) throw new Error(data.message || '删除家庭菜单失败');
}

// generateShoppingList 根据指定日期范围内的家庭菜单生成购物清单。
export async function generateShoppingList(params: {
  family_id: number;
  start_date: string;
  end_date: string;
  name?: string;
}) {
  const { data } = await api.post<ApiResponse & {
    shopping_list: ShoppingListInfo;
    items: ShoppingItemInfo[];
  }>('/family/shopping-lists/generate', params);
  if (data.code !== 0) throw new Error(data.message || '生成购物清单失败');
  return { list: data.shopping_list, items: data.items ?? [] };
}

// listShoppingLists 查询当前家庭已有购物清单。
export async function listShoppingLists(familyId: number) {
  const { data } = await api.get<ApiResponse & { shopping_lists: ShoppingListInfo[] }>(
    '/family/shopping-lists', { params: { family_id: familyId } },
  );
  if (data.code !== 0) throw new Error(data.message || '查询购物清单失败');
  return data.shopping_lists ?? [];
}

// getShoppingList 查询购物清单及其项目。
export async function getShoppingList(listId: number) {
  const { data } = await api.get<ApiResponse & {
    shopping_list: ShoppingListInfo;
    items: ShoppingItemInfo[];
  }>(`/family/shopping-lists/${listId}`);
  if (data.code !== 0) throw new Error(data.message || '查询购物清单详情失败');
  return { list: data.shopping_list, items: data.items ?? [] };
}

// updateShoppingItemPurchased 更新项目的已购买状态。
export async function updateShoppingItemPurchased(itemId: number, purchasedQuantity: number, isPurchased: boolean) {
  const { data } = await api.patch<ApiResponse>(`/family/shopping-list-items/${itemId}`, {
    purchased_quantity: purchasedQuantity,
    is_purchased: isPurchased,
  });
  if (data.code !== 0) throw new Error(data.message || '更新购买状态失败');
}

// addManualShoppingItem 添加一个手动购物项目。
export async function addManualShoppingItem(params: {
  shopping_list_id: number;
  ingredient_name: string;
  quantity?: number;
  quantity_text?: string;
  unit?: string;
}) {
  const { data } = await api.post<ApiResponse & { item: ShoppingItemInfo }>(
    '/family/shopping-list-items', params,
  );
  if (data.code !== 0) throw new Error(data.message || '添加购物项目失败');
  return data.item;
}

// deleteShoppingItem 删除购物清单项目。
export async function deleteShoppingItem(itemId: number) {
  const { data } = await api.delete<ApiResponse>(`/family/shopping-list-items/${itemId}`);
  if (data.code !== 0) throw new Error(data.message || '删除购物项目失败');
}
