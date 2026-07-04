import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import { API_BASE_URL } from '../config';

const TOKEN_KEY = 'auth_token';
const USER_ID_KEY = 'auth_user_id';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * 请求拦截器：自动附加 JWT Token
 */
api.interceptors.request.use(
  async (config) => {
    try {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
      // SecureStore 不可用时静默跳过 (Expo Go 开发模式)
    }
    return config;
  },
  (error) => Promise.reject(error),
);

/**
 * 响应拦截器：统一处理 401
 */
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      try {
        await SecureStore.deleteItemAsync(TOKEN_KEY);
      } catch {
        // ignore
      }
    }
    return Promise.reject(error);
  },
);

// Token 管理
export async function saveToken(token: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
  } catch {
    // Expo Go 降级方案
  }
}

export async function getToken(): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function removeToken(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(USER_ID_KEY);
  } catch {
    // ignore
  }
}

export async function saveUserId(userId: number): Promise<void> {
  try {
    await SecureStore.setItemAsync(USER_ID_KEY, String(userId));
  } catch {
    // ignore
  }
}

export async function getUserId(): Promise<number | null> {
  try {
    const val = await SecureStore.getItemAsync(USER_ID_KEY);
    return val ? Number(val) : null;
  } catch {
    return null;
  }
}

export default api;
