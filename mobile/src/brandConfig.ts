// 品牌包构建时由 deploy/multi-tenant/build-brands.sh 覆写；母版与本地开发保持 null（行为不变）
export const BRAND: {
  slug: string;
  name: string; // 公司全称（登录页品牌块 / 关于页）
  short: string; // 简称
  appName: string; // App 显示名（2026-09-29 定稿统一：医智代表/医智医生，全品牌一致；Android 桌面名固定在 strings.xml）
  primary: string; // 品牌主色 #RRGGBB
  char: string; // 字标首字
  tagline: string; // 副标语
  apiPort: number; // 该租户 web 入口端口（8801-8805），全部流量走它
} | null = null;
