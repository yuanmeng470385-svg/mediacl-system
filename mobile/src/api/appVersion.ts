/**
 * App 版本检查 API（2026-09-15 挂账：版本检查+更新提示）
 *
 * 公开端点（无需 token）—— 冷启动第一屏是登录页，此时还没登录也要能查版本。
 * 版本号/下载地址/更新说明都在后端 app_versions 表里，web 管理端「系统配置」可改。
 */
import { apiClient } from './client';

export interface AppVersionInfo {
  platform: string;
  platform_label?: string;
  /** 最新版本：本机低于它 → 提示更新（可跳过） */
  latest_version: string;
  /** 最低可用版本：本机低于它 → 强制更新（不更新不能用） */
  min_version: string;
  /** /apk/xxx.apk 相对路径或 http(s) 绝对地址，用 resolveDownloadUrl 补全 */
  download_url: string;
  release_notes?: string | null;
  updated_at?: string | null;
}

export const appVersionAPI = {
  check: (platform: 'rep' | 'doctor') =>
    apiClient.request<AppVersionInfo>('GET', '/api/v1/app/version', { platform }, 10000),
};
