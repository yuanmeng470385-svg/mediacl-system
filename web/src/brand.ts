// 多租户品牌：web 代理按实例返回 /brand.json（各公司名），本地开发无此文件时回退 MedAgent
export interface BrandInfo {
  name: string; // 公司全称：版权行 / 登录卡 / 分享落地页
  short?: string; // 简称：标签页标题 / 侧栏（缺省用全称）
}

export const BRAND_FALLBACK: BrandInfo = { name: 'MedAgent' };

let cached: BrandInfo = BRAND_FALLBACK;

export async function loadBrand(): Promise<BrandInfo> {
  try {
    const res = await fetch('/brand.json', { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (data && typeof data.name === 'string' && data.name) {
        cached = {
          name: data.name,
          short: typeof data.short === 'string' && data.short ? data.short : undefined,
        };
      }
    }
  } catch {
    // 本地 vite dev 无 /brand.json → 保持 MedAgent
  }
  document.title = `${cached.short || cached.name} - 管理后台`;
  return cached;
}

export function getBrand(): BrandInfo {
  return cached;
}
