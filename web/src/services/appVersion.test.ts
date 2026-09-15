/**
 * App 版本工具函数（与后端同口径的校验/比较）：格式、比较、下载地址。
 * 后端 app_version.py 的 VERSION_RE / parse_version / _validate_download_url 是同一套规则，
 * 这里放前端副本只为表单即时校验（避免提交后才报错），两边改一处要同步另一处。
 */
import { describe, expect, it } from 'vitest';
import { compareVersion, isDownloadUrl, isVersionString } from './appVersion';

describe('isVersionString', () => {
  it('接受 x.y.z，拒绝少一段/多一段/带前缀/空值', () => {
    expect(isVersionString('1.0.0')).toBe(true);
    expect(isVersionString(' 12.34.56 ')).toBe(true);
    for (const bad of ['1.0', '1', 'v1.0.0', '1.0.0.0', '1.0.x', '', undefined, '1..0']) {
      expect(isVersionString(bad as string), String(bad)).toBe(false);
    }
  });
});

describe('compareVersion', () => {
  it('按数值逐段比较（不是字符串比较）', () => {
    expect(compareVersion('1.2.0', '1.10.0')).toBeLessThan(0);
    expect(compareVersion('2.0.0', '1.9.9')).toBeGreaterThan(0);
    expect(compareVersion('1.0.0', '1.0.0')).toBe(0);
    expect(compareVersion('1.0.10', '1.0.9')).toBeGreaterThan(0);
  });
});

describe('isDownloadUrl', () => {
  it('放行相对路径与 http(s)，拦住裸文件名/协议相对', () => {
    expect(isDownloadUrl('/apk/medagent-rep.apk')).toBe(true);
    expect(isDownloadUrl('https://cdn.example.com/rep.apk')).toBe(true);
    expect(isDownloadUrl('http://39.96.52.114:8080/apk/medagent-rep.apk')).toBe(true);
    for (const bad of ['apk/rep.apk', 'ftp://x/rep.apk', '', undefined, '   ']) {
      expect(isDownloadUrl(bad as string), String(bad)).toBe(false);
    }
  });
});
