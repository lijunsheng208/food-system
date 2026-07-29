/**
 * 对应 proto/auth/v1/auth.proto 消息的类型定义
 */

export interface RegisterResponse {
  code: number;
  message: string;
  token: string;
  user_id: number;
}

export interface UserInfo {
  id: number;
  phone: string;
  nickname: string;
  avatar: string;
  gender: number;
  status: number;
  last_login_at: string;
  created_at: string;
  updated_at: string;
}

export interface LoginResponse {
  code: number;
  message: string;
  token: string;
  user: UserInfo;
}

/** 业务错误码映射 */
export const ErrorCode = {
  Success: 0,
  InvalidPhone: 1001,
  PasswordTooShort: 1002,
  PhoneExists: 1003,
  UserNotFound: 1004,
  PasswordWrong: 1005,
  UserDisabled: 1006,
  InternalError: 1999,
} as const;

export const ErrorMessages: Record<number, string> = {
  [ErrorCode.InvalidPhone]: '手机号格式不正确',
  [ErrorCode.PasswordTooShort]: '密码长度不能少于6位',
  [ErrorCode.PhoneExists]: '该手机号已注册',
  [ErrorCode.UserNotFound]: '账号不存在',
  [ErrorCode.PasswordWrong]: '密码错误',
  [ErrorCode.UserDisabled]: '账号已被禁用',
  [ErrorCode.InternalError]: '服务异常，请稍后重试',
};

export type AuthStackParamList = {
  Login: undefined;
  Register: undefined;
  Main: undefined;
  RecipeDetail: {
    dishId: number;
    dishName?: string;
  };
  CookingMode: {
    dishId: number;
    dishName: string;
    servings: number;
  };
  ProfileDetail: undefined;
  FamilyManagement: undefined;
  CreateFamily: undefined;
  EditFamily: {
    familyId: number;
    name: string;
    description: string;
    avatar: string;
  };
  JoinFamily: { inviteCode?: string };
  FamilyMemberEdit: {
    familyId: number;
    member: {
      user_id: number;
      nickname: string;
      avatar: string;
      role: number;
      relation: string;
      display_name: string;
    };
    myRole: number;
  };
};

export type MainTabParamList = {
  HomeTab: undefined;
  Recipes: undefined;
  Profile: undefined;
};
