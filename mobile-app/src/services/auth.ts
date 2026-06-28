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
