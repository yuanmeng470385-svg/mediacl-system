/**
 * 版本比较与下载地址补全（2026-09-15 挂账：App 版本检查+更新提示）
 * 与后端 app_versions 的号段口径一致：x.y.z 逐段按数值比，不是字符串比。
 */
import {
  APP_VERSION, compareVersion, hasUpdate, isForcedUpdate, normalizeVersion, resolveDownloadUrl,
} from '../appVersion';

describe('compareVersion', () => {
  it('逐段按数值比较（1.10.0 比 1.9.0 新，字符串比会判反）', () => {
    expect(compareVersion('1.10.0', '1.9.0')).toBeGreaterThan(0);
    expect(compareVersion('1.0.0', '1.0.1')).toBeLessThan(0);
    expect(compareVersion('2.0.0', '2.0.0')).toBe(0);
  });

  it('容忍 v 前缀、空格、段数不一致', () => {
    expect(compareVersion('v1.2.3', '1.2.3')).toBe(0);
    expect(compareVersion(' 1.2.3 ', '1.2.3')).toBe(0);
    expect(compareVersion('1.2', '1.2.0')).toBe(0);
    expect(compareVersion('1.2.0.1', '1.2.0')).toBeGreaterThan(0);
  });

  it('空值/垃圾值按 0 处理，不抛异常', () => {
    expect(compareVersion(null, '1.0.0')).toBeLessThan(0);
    expect(compareVersion('', '')).toBe(0);
    expect(compareVersion(undefined, 'x.y.z')).toBe(0);
  });
});

describe('hasUpdate / isForcedUpdate', () => {
  it('低于最新 → 有更新；低于最低 → 强制更新', () => {
    expect(hasUpdate('1.0.0', '1.0.1')).toBe(true);
    expect(hasUpdate('1.0.0', '1.0.0')).toBe(false);
    expect(hasUpdate('1.0.0', null)).toBe(false);

    expect(isForcedUpdate('1.0.0', '1.1.0')).toBe(true);
    expect(isForcedUpdate('1.1.0', '1.1.0')).toBe(false);
    expect(isForcedUpdate('1.0.0', null)).toBe(false); // min 未配 = 不强制
  });
});

describe('normalizeVersion', () => {
  it('去空格与 v 前缀', () => {
    expect(normalizeVersion(' V1.2.3 ')).toBe('1.2.3');
  });
});

describe('resolveDownloadUrl', () => {
  it('相对路径补成服务器地址（APK 在 web 8080，不在网关 8000）', () => {
    expect(resolveDownloadUrl('/apk/medagent-doctor.apk')).toMatch(/^http:\/\/.+:8080\/apk\/medagent-doctor\.apk$/);
    expect(resolveDownloadUrl('apk/medagent-doctor.apk')).toMatch(/^http:\/\/.+:8080\/apk\/medagent-doctor\.apk$/);
  });

  it('http(s) 绝对地址原样返回（换域名后由管理端填完整地址）', () => {
    expect(resolveDownloadUrl('https://cdn.example.com/rep.apk')).toBe('https://cdn.example.com/rep.apk');
  });

  it('空值返回空串', () => {
    expect(resolveDownloadUrl(null)).toBe('');
    expect(resolveDownloadUrl('  ')).toBe('');
  });
});

describe('APP_VERSION', () => {
  it('取自 package.json，且是 x.y.z 形状（后端按这个格式校验）', () => {
    expect(APP_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
  });
});
