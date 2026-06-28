import { TextStyle } from 'react-native';

/**
 * FamilyOS 字体系统
 *
 * 使用系统原生字体，通过尺寸和字重区分层级。
 * 避免使用 AI 默认的 Inter 字体组合。
 */

export const typography: Record<string, TextStyle> = {
  // 页面大标题 — "FamilyOS"
  h1: {
    fontSize: 32,
    fontWeight: '700',
    lineHeight: 40,
    letterSpacing: -0.5,
  },

  // 卡片标题 / 问候语
  h2: {
    fontSize: 20,
    fontWeight: '600',
    lineHeight: 28,
    letterSpacing: -0.3,
  },

  // 正文、输入框文字
  body: {
    fontSize: 16,
    fontWeight: '400',
    lineHeight: 24,
  },

  // 标签、提示文字
  caption: {
    fontSize: 13,
    fontWeight: '500',
    lineHeight: 18,
  },

  // 按钮文字
  button: {
    fontSize: 16,
    fontWeight: '600',
    lineHeight: 24,
  },
} as const;
