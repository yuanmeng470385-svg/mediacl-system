/**
 * 夜间简报 API 契约测试：锁定 URL/method/查询参数形状。
 * 后端 /api/v1/briefings：list 分页（page/page_size），getDetail 取 {id}。
 */
import { briefingAPI } from '../briefing';

const okResponse = (data: any = {}) => ({
  json: async () => ({ code: 0, message: 'success', data }),
});

let fetchMock: jest.Mock;

beforeEach(() => {
  fetchMock = jest.fn().mockResolvedValue(okResponse());
  (global as any).fetch = fetchMock;
});

/** 取出最近一次 fetch 的 url / method / body(已解析) */
function lastCall() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return {
    url: url as string,
    method: init.method as string,
    body: init.body ? JSON.parse(init.body as string) : undefined,
  };
}

describe('briefingAPI', () => {
  it('list 显式 page/page_size 作为查询参数透传（GET /api/v1/briefings）', async () => {
    await briefingAPI.list(2, 10);
    const c = lastCall();
    expect(c.url).toContain('/api/v1/briefings');
    expect(c.url).toContain('page=2');
    expect(c.url).toContain('page_size=10');
    expect(c.method).toBe('GET');
  });

  it('list 缺省走 page=1/page_size=20', async () => {
    await briefingAPI.list();
    const c = lastCall();
    expect(c.url).toContain('/api/v1/briefings');
    expect(c.url).toContain('page=1');
    expect(c.url).toContain('page_size=20');
  });

  it('getDetail 发 GET /api/v1/briefings/{id}', async () => {
    await briefingAPI.getDetail(123);
    const c = lastCall();
    expect(c.url).toContain('/api/v1/briefings/123');
    expect(c.method).toBe('GET');
    expect(c.body).toBeUndefined();
  });
});
