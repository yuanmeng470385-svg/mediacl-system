// 多租户品牌：web 代理按实例返回 /brand.json（公司名/主色/字标/标语），本地开发无此文件时回退 MedAgent
export interface BrandInfo {
  name: string; // 公司全称：版权行 / 登录卡 / 分享落地页 / 页头
  short?: string; // 简称：标签页标题 / 侧栏 / 登录卡（缺省用全称）
  primary?: string; // 品牌主色 #RRGGBB：全局主题色 / 登录页渐变 / 字标底色
  logoChar?: string; // 字标首字（缺省取简称/全称首字）
  tagline?: string; // 登录卡副标语
}

export const BRAND_FALLBACK: BrandInfo = { name: 'MedAgent' };

let cached: BrandInfo = BRAND_FALLBACK;

function sanitizePrimary(v: unknown): string | undefined {
  return typeof v === 'string' && /^#[0-9A-Fa-f]{6}$/.test(v) ? v : undefined;
}

function injectFavicon(b: BrandInfo) {
  // 字标色块动态 favicon：5 家后台同开时标签页一眼可辨；MedAgent 回退态保留构建自带图标
  const primary = b.primary;
  if (!primary) return;
  const char = (b.logoChar || b.short || b.name || 'M').replace(/[^一-龥A-Za-z0-9]/g, '').slice(0, 1) || 'M';
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">' +
    `<rect width="64" height="64" rx="14" fill="${primary}"/>` +
    `<text x="32" y="44" font-size="34" font-family="PingFang SC, Microsoft YaHei, sans-serif" fill="#fff" text-anchor="middle" font-weight="600">${char}</text>` +
    '</svg>';
  const href = 'data:image/svg+xml,' + encodeURIComponent(svg);
  let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']");
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  link.href = href;
}

export async function loadBrand(): Promise<BrandInfo> {
  try {
    const res = await fetch('/brand.json', { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (data && typeof data.name === 'string' && data.name) {
        cached = {
          name: data.name,
          short: typeof data.short === 'string' && data.short ? data.short : undefined,
          primary: sanitizePrimary(data.primary),
          logoChar: typeof data.logoChar === 'string' && data.logoChar ? data.logoChar.slice(0, 1) : undefined,
          tagline: typeof data.tagline === 'string' && data.tagline ? data.tagline : undefined,
        };
      }
    }
  } catch {
    // 本地 vite dev 无 /brand.json → 保持 MedAgent
  }
  document.title = `${cached.short || cached.name} - 管理后台`;
  injectFavicon(cached);
  return cached;
}

export function getBrand(): BrandInfo {
  return cached;
}
