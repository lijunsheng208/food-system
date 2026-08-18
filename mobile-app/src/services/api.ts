import axios, { type InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { API_BASE_URL } from '../config';

const ACCESS_TOKEN_KEY = 'auth_access_token';
const REFRESH_TOKEN_KEY = 'auth_refresh_token';
const ACCESS_TOKEN_EXPIRES_AT_KEY = 'auth_access_token_expires_at';
const DEVICE_ID_KEY = 'auth_device_id';

// expo-secure-store 没有 Web 实现；Web 开发环境使用 AsyncStorage，原生端仍使用系统安全存储。
async function setStoredValue(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    await AsyncStorage.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function getStoredValue(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    return AsyncStorage.getItem(key);
  }
  return SecureStore.getItemAsync(key);
}

async function deleteStoredValue(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    await AsyncStorage.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

type RetryableRequestConfig = InternalAxiosRequestConfig & {
  _authRetry?: boolean;
};

let refreshPromise: Promise<string> | null = null;
let authFailureHandler: (() => void) | null = null;

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

// 独立实例避免刷新接口进入业务响应拦截器并形成循环。
const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use(async (config) => {
  const accessToken = await getAccessToken();
  if (accessToken && config.headers) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config as RetryableRequestConfig | undefined;
    if (error.response?.status !== 401 || !original) {
      return Promise.reject(error);
    }
    if (original.url?.includes('/auth/refresh')) {
      return Promise.reject(error);
    }
    if (original._authRetry) {
      await clearAuthCredentials();
      authFailureHandler?.();
      return Promise.reject(error);
    }

    original._authRetry = true;
    try {
      const accessToken = await refreshAccessTokenOnce();
      original.headers.Authorization = `Bearer ${accessToken}`;
      return api.request(original);
    } catch (refreshError) {
      return Promise.reject(refreshError);
    }
  },
);

async function refreshAccessTokenOnce(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = await getRefreshToken();
      if (!refreshToken) throw new Error('missing refresh token');

      const { data } = await authApi.post<AuthTokens & { code: number; message: string }>(
        '/auth/refresh',
        { refresh_token: refreshToken },
      );
      if (data.code !== 0 || !data.access_token || !data.refresh_token) {
        throw new Error(data.message || 'token refresh failed');
      }
      await saveAuthTokens(data);
      return data.access_token;
    })()
      .catch(async (error) => {
        await clearAuthCredentials();
        authFailureHandler?.();
        throw error;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export function setAuthFailureHandler(handler: (() => void) | null): void {
  authFailureHandler = handler;
}

export async function saveAuthTokens(tokens: AuthTokens): Promise<void> {
  const expiresAt = Date.now() + Math.max(tokens.expires_in, 0) * 1000;
  try {
    await Promise.all([
      setStoredValue(ACCESS_TOKEN_KEY, tokens.access_token),
      setStoredValue(REFRESH_TOKEN_KEY, tokens.refresh_token),
      setStoredValue(ACCESS_TOKEN_EXPIRES_AT_KEY, String(expiresAt)),
    ]);
  } catch (error) {
    await clearAuthCredentials();
    throw error;
  }
}

export async function getAccessToken(): Promise<string | null> {
  try {
    return await getStoredValue(ACCESS_TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function getRefreshToken(): Promise<string | null> {
  try {
    return await getStoredValue(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function getAccessTokenExpiresAt(): Promise<number | null> {
  try {
    const value = await getStoredValue(ACCESS_TOKEN_EXPIRES_AT_KEY);
    return value ? Number(value) : null;
  } catch {
    return null;
  }
}

export async function clearAuthCredentials(): Promise<void> {
  try {
    await Promise.all([
      deleteStoredValue(ACCESS_TOKEN_KEY),
      deleteStoredValue(REFRESH_TOKEN_KEY),
      deleteStoredValue(ACCESS_TOKEN_EXPIRES_AT_KEY),
    ]);
  } catch {
    // 凭证清理是 best-effort，导航仍需回到登录页。
  }
}

// logoutAndClear 先清理本地凭证，再异步通知服务端撤销刷新会话，避免网络异常阻塞退出。
export async function logoutAndClear(): Promise<void> {
  const refreshToken = await getRefreshToken();
  await clearAuthCredentials();

  if (refreshToken) {
    // 服务端注销属于 best-effort；本地退出完成后无需等待网络响应。
    void authApi.post('/auth/logout', { refresh_token: refreshToken }).catch(() => undefined);
  }
}

export async function getOrCreateDeviceID(): Promise<string> {
  try {
    const existing = await getStoredValue(DEVICE_ID_KEY);
    if (existing) return existing;
    const created = `mobile-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
    await setStoredValue(DEVICE_ID_KEY, created);
    return created;
  } catch {
    return `mobile-${Date.now()}`;
  }
}

export default api;
