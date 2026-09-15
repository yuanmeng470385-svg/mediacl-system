/**
 * App 版本检查 API 契约测试（2026-09-15 挂账）：
 * 锁定 URL / method / 查询参数，断言 fetch 最后一通调用。
 */
import { appVersionAPI } from '../appVersion';

const okResponse = (data: any = {}) => ({ json: async () => ({ code: 0, message: 'success', data }) });
let fetchMock: jest.Mock;
beforeEach(() => {
  fetchMock = jest.fn().mockResolvedValue(okResponse());
  (global as any).fetch = fetchMock;
});
function lastCall() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return { url: String(url), init };
}

describe('appVersion API', () => {
  it('check 发 GET /api/v1/app/version?platform=doctor（无 token 也要能发出去）', async () => {
    fetchMock.mockResolvedValue(okResponse({
      platform: 'doctor',
      latest_version: '1.2.0',
      min_version: '1.1.0',
      download_url: '/apk/medagent-doctor.apk',
      release_notes: '新增 AI 助手',
    }));
    const res = await appVersionAPI.check('doctor');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/app/version');
    expect(url).toContain('platform=doctor');
    expect((init?.method || 'GET').toUpperCase()).toBe('GET');
    // 响应形状直取后端字段（不做驼峰映射：两端契约就是 snake_case）
    expect(res.latest_version).toBe('1.2.0');
    expect(res.min_version).toBe('1.1.0');
    expect(res.download_url).toBe('/apk/medagent-doctor.apk');
  });
});
