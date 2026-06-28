/**
 * FamilyOS 色彩系统
 *
 * 以蓝色为核心主色，蓝色调背景替代模板化的奶油色背景。
 * 避开了 AI 生成的三种默认风格。
 */

export const colors = {
  // 主色
  primary: '#1A56DB',       // 深沉蓝 — 主按钮、链接
  primaryDark: '#1E40AF',   // 深蓝 — 按压态
  primaryLight: '#DBEAFE',  // 浅蓝 — 选中背景
  primarySubtle: '#EFF6FF', // 极浅蓝 — 卡片内背景

  // 背景与表面
  background: '#F0F4FF',    // 蓝调白 — 页面背景 (替代 cream #F4F1EA)
  surface: '#FFFFFF',       // 纯白 — 卡片、输入框

  // 文字
  textPrimary: '#111827',   // 近黑 — 标题、正文
  textSecondary: '#6B7280', // 中灰 — 标签、提示
  textOnPrimary: '#FFFFFF', // 白色 — 主按钮上的文字

  // 边框
  border: '#D1D5DB',          // 灰边框
  borderFocus: '#1A56DB',     // 聚焦时的蓝色边框

  // 状态
  error: '#DC2626',          // 红 — 错误文字、错误边框
  errorBackground: '#FEF2F2',// 浅红背景
  success: '#059669',        // 绿 — 成功提示

} as const;
