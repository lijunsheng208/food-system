/**
 * 应用配置
 *
 * API_HOST: 网关地址。真机扫码改为电脑局域网 IP；模拟器用 10.0.2.2。
 */

// 你的电脑局域网 IP（真机 Expo Go 扫码用这个）
const DEV_HOST = '192.168.1.5';

// Android 模拟器用 10.0.2.2，iOS 模拟器用 localhost
const EMULATOR_HOST = '10.0.2.2';

export const API_BASE_URL = `http://${DEV_HOST}:8080/api/v1`;
