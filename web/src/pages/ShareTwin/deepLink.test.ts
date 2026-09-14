import { describe, it, expect } from 'vitest';
import { TWIN_DEEP_LINK_PREFIX, buildTwinDeepLink, normalizeShareToken } from './deepLink';

describe('ShareTwin deepLink（部署挂账 §4）', () => {
  it('深链拼装：medagent-doctor://twin/ + token', () => {
    expect(TWIN_DEEP_LINK_PREFIX).toBe('medagent-doctor://twin/');
    expect(buildTwinDeepLink('abc123')).toBe('medagent-doctor://twin/abc123');
  });

  it('normalizeShareToken：32 位 hex 放行（ShareLink.url_token = uuid4().hex）', () => {
    const token = '0f1e2d3c4b5a69788796a5b4c3d2e1f0';
    expect(normalizeShareToken(token)).toBe(token);
    expect(normalizeShareToken(`  ${token}  `)).toBe(token); // 手抄/URL 带空格容错
  });

  it('normalizeShareToken：非法形态判无效（null）', () => {
    expect(normalizeShareToken(undefined)).toBeNull();
    expect(normalizeShareToken('')).toBeNull();
    expect(normalizeShareToken('short')).toBeNull();          // 长度不对
    expect(normalizeShareToken('Z'.repeat(32))).toBeNull();    // 非 hex
    expect(normalizeShareToken('0f1e2d3c4b5a69788796a5b4c3d2e1f')).toBeNull(); // 31 位
  });
});
