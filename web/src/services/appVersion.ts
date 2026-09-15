import client from './client';
import type { ApiResponse } from '../types';

/** 两端 App（代表端 rep / 医生端 doctor）的版本与更新提示配置 */
export type AppPlatform = 'rep' | 'doctor';

export interface AppVersionItem {
  platform: AppPlatform;
  platform_label: string;
  /** 最新版本：App 本机版本低于它即弹「发现新版本」 */
  latest_version: string;
  /** 最低可用版本：App 本机版本低于它则强制更新（不更新不能用），别乱抬 */
  min_version: string;
  /** APK 下载地址：/apk/xxx.apk 相对路径（App 自动补服务器地址）或 http(s) 绝对地址 */
  download_url: string;
  release_notes?: string | null;
  updated_at?: string | null;
}

export interface AppVersionUpdate {
  latest_version?: string;
  min_version?: string;
  download_url?: string;
  release_notes?: string | null;
}

/** 版本号格式 x.y.z（与后端 app_version.py 的 VERSION_RE 同口径） */
export const isVersionString = (v?: string): boolean => /^\d+\.\d+\.\d+$/.test((v ?? '').trim());

/** 版本号比较（a>b 返正数）；仅在格式合法时使用，用于「最低版本不得高于最新版本」的即时校验 */
export function compareVersion(a: string, b: string): number {
  const pa = a.trim().split('.').map(Number);
  const pb = b.trim().split('.').map(Number);
  for (let i = 0; i < 3; i += 1) {
    const diff = (pa[i] || 0) - (pb[i] || 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

/** 下载地址：以 / 开头的相对路径，或 http(s) 绝对地址 */
export const isDownloadUrl = (v?: string): boolean => {
  const text = (v ?? '').trim();
  return text.startsWith('/') || text.startsWith('http://') || text.startsWith('https://');
};

export const appVersionAPI = {
  /** 两端版本配置（admin；GET /api/v1/app/config） */
  list: () => client.get<ApiResponse<AppVersionItem[]>>('/app/config'),
  /** 改某端版本配置（admin；PUT /api/v1/app/config/{platform}，只传要改的字段） */
  update: (platform: AppPlatform, payload: AppVersionUpdate) =>
    client.put<ApiResponse<AppVersionItem>>(`/app/config/${platform}`, payload),
};
