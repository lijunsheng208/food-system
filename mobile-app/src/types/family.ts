/**
 * 家庭模块类型定义
 *
 * 对应 proto/family/v1/family.proto 消息定义
 */

export type FamilyRole = 1 | 2 | 3;

/** 家庭信息 */
export interface FamilyInfo {
  id: number;
  name: string;
  avatar: string;
  description: string;
  owner_user_id: number;
  invite_code: string;
  member_count: number;
  max_member_count: number;
  my_role: FamilyRole;
  created_at: string;
  updated_at: string;
}

/** 家庭成员信息 */
export interface FamilyMemberInfo {
  user_id: number;
  phone: string;
  nickname: string;
  avatar: string;
  role: FamilyRole;
  relation: string;
  display_name: string;
  joined_at: string;
}

/** 通用 API 响应 */
export interface ApiResponse {
  code: number;
  message: string;
}

/** 角色常量 */
export const FamilyRoleLabel: Record<FamilyRole, string> = {
  1: '所有者',
  2: '管理员',
  3: '成员',
};

/** 业务错误码 */
export const FamilyErrorCode = {
  Success: 0,
  FamilyNotFound: 2001,
  UserAlreadyInFamily: 2002,
  UserNotInFamily: 2003,
  NoPermission: 2004,
  InvalidInviteCode: 2005,
  FamilyFull: 2006,
  CannotOperateOwner: 2007,
  InvalidFamilyName: 2008,
  MemberNotFound: 2009,
} as const;

export const FamilyErrorMessages: Record<number, string> = {
  [FamilyErrorCode.FamilyNotFound]: '家庭不存在',
  [FamilyErrorCode.UserAlreadyInFamily]: '你已经加入了一个家庭',
  [FamilyErrorCode.UserNotInFamily]: '你还没有加入家庭',
  [FamilyErrorCode.NoPermission]: '你没有权限进行此操作',
  [FamilyErrorCode.InvalidInviteCode]: '邀请码无效或已过期',
  [FamilyErrorCode.FamilyFull]: '该家庭成员数量已满',
  [FamilyErrorCode.CannotOperateOwner]: '不能操作家庭所有者',
  [FamilyErrorCode.InvalidFamilyName]: '请输入正确的家庭名称',
  [FamilyErrorCode.MemberNotFound]: '成员不存在',
};
