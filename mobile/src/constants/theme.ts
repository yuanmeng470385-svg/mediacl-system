/**
 * MedAgent 移动端 - 主题常量
 */

export const Colors = {
  // 主色
  primary: '#3b82f6',
  primaryLight: '#60a5fa',
  primaryDark: '#2563eb',

  // 语义色
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#dc2626',
  info: '#06b6d4',

  // 中性色
  white: '#ffffff',
  background: '#f5f5f5',
  card: '#ffffff',
  border: '#e5e7eb',
  divider: '#f0f0f0',

  // 文字
  textPrimary: '#111827',
  textSecondary: '#6b7280',
  textHint: '#9ca3af',
  textWhite: '#ffffff',
  textLink: '#3b82f6',

  // 证据等级标签
  evidenceA: '#22c55e',
  evidenceB: '#3b82f6',
  evidenceC: '#f59e0b',
  evidenceD: '#dc2626',

  // 情感色
  sentimentPositive: '#22c55e',
  sentimentNeutral: '#6b7280',
  sentimentNegative: '#dc2626',

  // Tab
  tabActive: '#3b82f6',
  tabInactive: '#999999',
} as const;

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const FontSize = {
  xs: 11,
  sm: 13,
  md: 15,
  lg: 17,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const BorderRadius = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  full: 999,
} as const;

export const Shadow = {
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
  },
  button: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.12,
    shadowRadius: 4,
    elevation: 3,
  },
} as const;
