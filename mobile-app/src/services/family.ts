/**
 * 家庭模块 API 服务
 *
 * 所有接口对接 gateway-service /api/v1/family/*
 * 后续接入 JWT 中间件后，后端从 Token 解析用户 ID，
 * 届时可移除请求中的 user_id 参数。
 */

import api from './api';
import type {
  FamilyInfo,
  FamilyMemberInfo,
  ApiResponse,
  FamilyMealPlanInfo,
  MealType,
} from '../types/family';

// ─── 查询我的家庭 ────────────────────────────────────────────

export async function getMyFamily(userId: number) {
  const { data } = await api.get<{
    code: number;
    message: string;
    family: FamilyInfo | null;
  }>('/family/my', { params: { user_id: userId } });
  if (data.code !== 0) throw new Error(data.message || '查询家庭失败');
  return data.family;
}

// ─── 创建家庭 ──────────────────────────────────────────────────

export async function createFamily(params: {
  user_id: number;
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
  user_id: number;
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
  user_id: number;
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

export async function leaveFamily(userId: number) {
  const { data } = await api.post<ApiResponse>('/family/leave', {
    user_id: userId,
  });
  if (data.code !== 0) throw new Error(data.message || '退出家庭失败');
  return data;
}

// ─── 解散家庭 ──────────────────────────────────────────────────

export async function dissolveFamily(familyId: number, userId: number) {
  const { data } = await api.delete<ApiResponse>(`/family/${familyId}`, {
    data: { user_id: userId },
  });
  if (data.code !== 0) throw new Error(data.message || '解散家庭失败');
  return data;
}

// ─── 查询家庭成员列表 ──────────────────────────────────────────

export async function listFamilyMembers(
  familyId: number,
  userId: number,
) {
  const { data } = await api.get<{
    code: number;
    message: string;
    members: FamilyMemberInfo[];
  }>(`/family/${familyId}/members`, { params: { user_id: userId } });
  if (data.code !== 0) throw new Error(data.message || '查询成员失败');
  return data.members;
}

// ─── 修改成员信息 ──────────────────────────────────────────────

export async function updateMember(params: {
  family_id: number;
  operator_user_id: number;
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

export async function removeMember(
  familyId: number,
  operatorUserId: number,
  memberUserId: number,
) {
  const { data } = await api.delete<ApiResponse>(
    `/family/${familyId}/members/${memberUserId}`,
    { data: { operator_user_id: operatorUserId } },
  );
  if (data.code !== 0) throw new Error(data.message || '移除成员失败');
  return data;
}

// ─── 重置邀请码 ────────────────────────────────────────────────

export async function resetInviteCode(
  familyId: number,
  userId: number,
  expireHours?: number,
) {
  const { data } = await api.post<ApiResponse & {
    invite_code: string;
    invite_code_expired_at: string;
  }>(`/family/${familyId}/invite-code/reset`, {
    user_id: userId,
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
  created_by: number;
}) {
  const { data } = await api.post<ApiResponse & { meal_plan: FamilyMealPlanInfo }>(
    '/family/meal-plans', params,
  );
  if (data.code !== 0) throw new Error(data.message || '加入家庭菜单失败');
  return data.meal_plan;
}

export async function listMealPlans(
  familyId: number,
  userId: number,
  startDate: string,
  endDate: string,
) {
  const { data } = await api.get<ApiResponse & { meal_plans: FamilyMealPlanInfo[] }>(
    `/family/${familyId}/meal-plans`,
    { params: { user_id: userId, start_date: startDate, end_date: endDate } },
  );
  if (data.code !== 0) throw new Error(data.message || '查询家庭菜单失败');
  return data.meal_plans ?? [];
}

export async function updateMealPlan(
  id: number,
  params: {
    user_id: number;
    meal_date?: string;
    meal_type?: MealType;
    servings?: number;
    cook_user_id?: number;
  },
) {
  const { data } = await api.patch<ApiResponse & { meal_plan: FamilyMealPlanInfo }>(
    `/family/meal-plans/${id}`, params,
  );
  if (data.code !== 0) throw new Error(data.message || '修改家庭菜单失败');
  return data.meal_plan;
}

export async function deleteMealPlan(id: number, userId: number) {
  const { data } = await api.delete<ApiResponse>(`/family/meal-plans/${id}`, {
    params: { user_id: userId },
  });
  if (data.code !== 0) throw new Error(data.message || '删除家庭菜单失败');
}
