/**
 * MedAgent 移动端 - 临床精准风主题
 *
 * 设计理念：深海军蓝 + 纯白卡片 + 青蓝数据高亮
 * 对标医疗器械界面的冷静、专业、精确感
 */

// ==============================
// 主色调
// ==============================
import { BRAND } from '../brandConfig';

// 品牌包：整套品牌色由公司主色推导；母版/开发 BRAND=null 保持「临床精准风」原值不变
function hexMix(hex: string, target: string, t: number): string {
  const a = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const b = [1, 3, 5].map((i) => parseInt(target.slice(i, i + 2), 16));
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');
}
const BP = BRAND ? BRAND.primary : '#0D3B66';
const BRAND_PRIMARY = BP;
const BRAND_PRIMARY_LIGHT = BRAND ? hexMix(BP, '#FFFFFF', 0.2) : '#1565C0';
const BRAND_PRIMARY_DARK = BRAND ? hexMix(BP, '#000000', 0.3) : '#072540';
const BRAND_PRIMARY_SURFACE = BRAND ? hexMix(BP, '#FFFFFF', 0.92) : '#E8F0F8';

export const Colors = {
  // 品牌色——母版深海军蓝；品牌包时为各公司主色推导
  primary: BRAND_PRIMARY,
  primaryLight: BRAND_PRIMARY_LIGHT,
  primaryDark: BRAND_PRIMARY_DARK,
  primarySurface: BRAND_PRIMARY_SURFACE,

  // 数据高亮——青蓝
  accent: '#00ACC1',
  accentLight: '#E0F7FA',

  // 语义色——临床级
  success: '#2E7D32',
  successLight: '#E8F5E9',
  warning: '#F57C00',
  warningLight: '#FFF3E0',
  danger: '#C62828',
  dangerLight: '#FFEBEE',
  info: '#0288D1',
  infoLight: '#E1F5FE',

  // 中性色——冷白底
  white: '#FFFFFF',
  background: '#F0F2F5',
  backgroundAlt: '#F5F7FA',
  card: '#FFFFFF',
  border: '#DDE1E6',
  divider: '#E8ECF0',

  // 文字层级
  textPrimary: '#1A1C1E',
  textSecondary: '#5F6B7A',
  textHint: '#8E99A8',
  textWhite: '#FFFFFF',
  textLink: '#0D3B66',
  textOnPrimary: '#FFFFFF',

  // 证据等级——保留原语义
  evidenceA: '#2E7D32',
  evidenceB: '#0D3B66',
  evidenceC: '#F57C00',
  evidenceD: '#C62828',

  // 情感色
  sentimentPositive: '#2E7D32',
  sentimentNeutral: '#5F6B7A',
  sentimentNegative: '#C62828',

  // Tab 栏
  tabActive: '#0D3B66',
  tabInactive: '#8E99A8',
  tabBarBackground: '#FFFFFF',
} as const;

// ==============================
// 间距
// ==============================
export const Spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  huge: 48,
} as const;

// ==============================
// 字号——1.2 比例阶梯
// ==============================
export const FontSize = {
  xs: 11,
  sm: 13,
  md: 15,
  lg: 17,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  hero: 40,
} as const;

// ==============================
// 行高
// ==============================
export const LineHeight = {
  tight: 1.2,
  normal: 1.5,
  relaxed: 1.7,
} as const;

// ==============================
// 字重
// ==============================
export const FontWeight = {
  regular: '400' as const,
  medium: '500' as const,
  semibold: '600' as const,
  bold: '700' as const,
  heavy: '800' as const,
};

// ==============================
// 圆角
// ==============================
export const BorderRadius = {
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  xxl: 20,
  full: 999,
} as const;

// ==============================
// 阴影层级（临床精确深度）
// ==============================
export const Shadow = {
  // 卡片——悬浮 2dp
  card: {
    shadowColor: '#0D3B6610',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 3,
    elevation: 2,
  },
  // FAB——悬浮 6dp
  fab: {
    shadowColor: '#0D3B6625',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 1,
    shadowRadius: 6,
    elevation: 6,
  },
  // 按钮——悬浮 3dp
  button: {
    shadowColor: '#0D3B6615',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 3,
  },
  // 头部导航——悬浮 4dp
  header: {
    shadowColor: '#00000020',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 4,
  },
} as const;

// ==============================
// 动画时长
// ==============================
export const Duration = {
  fast: 150,
  normal: 250,
  slow: 400,
} as const;
