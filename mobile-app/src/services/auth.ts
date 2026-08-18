import api, { getOrCreateDeviceID, saveAuthTokens } from './api';
import type { RegisterResponse, LoginResponse, SMSLoginResponse } from '../types/auth';

/**
 * 用户注册
 */
export async function register(
  phone: string,
  password: string,
  nickname: string,
): Promise<RegisterResponse> {
  const deviceId = await getOrCreateDeviceID();
  const { data } = await api.post<RegisterResponse>('/auth/register', {
    phone,
    password,
    nickname,
    device_id: deviceId,
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
  const deviceId = await getOrCreateDeviceID();
  const { data } = await api.post<LoginResponse>('/auth/login', {
    phone,
    password,
    device_id: deviceId,
  });
  return data;
}

export interface SMSCodeResponse {
  code: number;
  message: string;
  retry_after_seconds: number;
}

/** 发送短信登录验证码 */
export async function sendSMSCode(phone: string): Promise<SMSCodeResponse> {
  const { data } = await api.post<SMSCodeResponse>('/auth/sms/code', { phone });
  return data;
}

/** 使用短信验证码登录；未注册手机号会由后端自动创建账号。 */
export async function smsLogin(
  phone: string,
  verificationCode: string,
): Promise<SMSLoginResponse> {
  const deviceId = await getOrCreateDeviceID();
  const { data } = await api.post<SMSLoginResponse>('/auth/sms/login', {
    phone,
    verification_code: verificationCode,
    device_id: deviceId,
  });
  if (data.code === 0 && data.access_token && data.refresh_token) {
    await saveAuthTokens(data);
  }
  return data;
}

/**
 * 注册成功后自动保存 Token
 */
export async function registerAndSaveCredentials(
  phone: string,
  password: string,
  nickname: string,
): Promise<RegisterResponse> {
  const resp = await register(phone, password, nickname);
  if (resp.code === 0 && resp.access_token && resp.refresh_token) {
    await saveAuthTokens(resp);
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
export async function getProfile() {
  const { data } = await api.get<ProfileResponse>('/auth/profile');
  if (data.code !== 0) {
    throw new Error(data.message || '查询失败');
  }
  return data;
}

/**
 * 更新用户个人信息
 */
export async function updateProfile(params: {
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
  uri: string,
  filename: string,
): Promise<string> {
  const formData = new FormData();
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
export async function loginAndSaveCredentials(
  phone: string,
  password: string,
): Promise<LoginResponse> {
  const resp = await login(phone, password);
  if (resp.code === 0 && resp.access_token && resp.refresh_token) {
    await saveAuthTokens(resp);
  }
  return resp;
}
