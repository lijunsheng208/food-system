/**
 * 前端校验 — 与后端 proto 规则保持一致
 */

/** 中国大陆手机号正则 (与后端一致: ^1[3-9]\\d{9}$) */
const PHONE_REGEX = /^1[3-9]\d{9}$/;

export function isValidPhone(phone: string): boolean {
  return PHONE_REGEX.test(phone);
}

export function isValidPassword(password: string): boolean {
  return password.length >= 6;
}

export type ValidationErrors = Record<string, string | undefined>;

/**
 * 注册表单校验
 */
export function validateRegister(params: {
  phone: string;
  password: string;
  nickname: string;
  confirmPassword: string;
}): ValidationErrors {
  const errors: ValidationErrors = {};

  if (!params.nickname.trim()) {
    errors.nickname = '请输入昵称';
  }

  if (!params.phone.trim()) {
    errors.phone = '请输入手机号';
  } else if (!isValidPhone(params.phone)) {
    errors.phone = '手机号格式不正确';
  }

  if (!params.password) {
    errors.password = '请输入密码';
  } else if (!isValidPassword(params.password)) {
    errors.password = '密码长度不能少于6位';
  }

  if (params.password !== params.confirmPassword) {
    errors.confirmPassword = '两次输入的密码不一致';
  }

  return errors;
}

/**
 * 登录表单校验
 */
export function validateLogin(params: {
  phone: string;
  password: string;
}): ValidationErrors {
  const errors: ValidationErrors = {};

  if (!params.phone.trim()) {
    errors.phone = '请输入手机号';
  } else if (!isValidPhone(params.phone)) {
    errors.phone = '手机号格式不正确';
  }

  if (!params.password) {
    errors.password = '请输入密码';
  }

  return errors;
}
