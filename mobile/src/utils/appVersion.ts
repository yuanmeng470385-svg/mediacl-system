/**
 * App 版本工具（2026-09-15 挂账：版本检查+更新提示）
 *
 * 版本号口径与后端 app_versions 表一致：x.y.z，逐段按数值比较（"1.10.0" > "1.9.0"）。
 * 本机版本取 package.json 的 version —— 与「我的 → 关于」展示的是同一个值，
 * 发新版时改 package.json（以及 android versionName/versionCode）即可。
 */
import { API_SCHEME, WEB_HOST, WEB_PORT } from '../config';

export const APP_VERSION: string = require('../../package.json').version;

/** 'v1.2.3' / ' 1.2.3 ' → '1.2.3'；非法输入原样返回（比较时按 0 处理） */
export function normalizeVersion(value?: string | null): string {
  return String(value ?? '').trim().replace(/^v/i, '');
}

/** 逐段数值比较：a<b → 负数，a==b → 0，a>b → 正数 */
export function compareVersion(a?: string | null, b?: string | null): number {
  const pa = normalizeVersion(a).split('.');
  const pb = normalizeVersion(b).split('.');
  const len = Math.max(pa.length, pb.length);
  for (let i = 0; i < len; i += 1) {
    const diff = (parseInt(pa[i] ?? '0', 10) || 0) - (parseInt(pb[i] ?? '0', 10) || 0);
    if (diff !== 0) return diff > 0 ? 1 : -1;
  }
  return 0;
}

/** 是否有更新：本机 < latest 才算有 */
export function hasUpdate(current: string, latest?: string | null): boolean {
  return !!latest && compareVersion(current, latest) < 0;
}

/** 是否强制更新：本机 < min 就得更新才能用（min 没配则不算强制） */
export function isForcedUpdate(current: string, min?: string | null): boolean {
  return !!min && compareVersion(current, min) < 0;
}

/**
 * 补全下载地址：后端存的是相对路径（/apk/medagent-rep.apk）时补上服务器地址
 * （web 静态资源在 8080，不在网关 8000）；已是 http(s) 绝对地址则原样返回。
 */
export function resolveDownloadUrl(url?: string | null): string {
  const text = String(url ?? '').trim();
  if (!text) return '';
  if (/^https?:\/\//i.test(text)) return text;
  return `${API_SCHEME}://${WEB_HOST}:${WEB_PORT}${text.startsWith('/') ? '' : '/'}${text}`;
}
