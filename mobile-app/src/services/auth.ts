import api, { saveToken } from './api';
import type { RegisterResponse, LoginResponse } from '../types/auth';

/**
 * 用户注册
 */
export async function register(
  phone: string,
  password: string,
  nickname: string,
): Promise<RegisterResponse> {
  const { data } = await api.post<RegisterResponse>('/auth/register', {
    phone,
    password,
    nickname,
  });
  return data;
}

/**
 * 用户登录
 */
export async function login(
  phone: string,
  password: string,
): Promise<LoginResponse> {
  const { data } = await api.post<LoginResponse>('/auth/login', {
    phone,
    password,
  });
  return data;
}

/**
 * 注册成功后自动保存 Token
 */
export async function registerAndSaveToken(
  phone: string,
  password: string,
  nickname: string,
): Promise<RegisterResponse> {
  const resp = await register(phone, password, nickname);
  if (resp.code === 0 && resp.token) {
    await saveToken(resp.token);
  }
  return resp;
}

interface ProfileResponse {
  code: number;
  message: string;
  user: import('../types/auth').UserInfo;
  family_name: string;
}

/**
 * 查询用户个人信息
 */
export async function getProfile(userId: number) {
  const { data } = await api.get<ProfileResponse>('/auth/profile', {
    params: { user_id: userId },
  });
  if (data.code !== 0) {
    throw new Error(data.message || '查询失败');
  }
  return data;
}

/**
 * 更新用户个人信息
 */
export async function updateProfile(params: {
  user_id: number;
  nickname?: string;
  avatar?: string;
  gender?: number;
}) {
  const { data } = await api.put<{ code: number; message: string }>(
    '/auth/profile',
    params,
  );
  if (data.code !== 0) {
    throw new Error(data.message || '更新失败');
  }
  return data;
}

/**
 * 上传头像到 OSS，返回 URL
 */
export async function uploadAvatar(
  userId: number,
  uri: string,
  filename: string,
): Promise<string> {
  const formData = new FormData();
  formData.append('user_id', String(userId));
  formData.append('file', {
    uri,
    name: filename,
    type: 'image/jpeg',
  } as any);

  const { data } = await api.post<{ code: number; message: string; url: string }>(
    '/upload/avatar',
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  if (data.code !== 0) {
    throw new Error(data.message || '上传失败');
  }
  return data.url;
}

/**
 * 登录成功后自动保存 Token
 */
export async function loginAndSaveToken(
  phone: string,
  password: string,
): Promise<LoginResponse> {
  const resp = await login(phone, password);
  if (resp.code === 0 && resp.token) {
    await saveToken(resp.token);
  }
  return resp;
}
