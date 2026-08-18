/**
 * 分身分享链接 API 契约测试：锁定 URL/method/body 形状。
 * 后端 specialist-service /api/v1/share-links（share_links 表），生成链接 body 为
 * {twin_id, expire_days?}，列表 GET 返回 ShareLinkItem[]。
 */
import { shareAPI } from '../share';

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

describe('shareAPI', () => {
  it('create 带 expireDays 发 POST /api/v1/share-links 且 body 为 {twin_id, expire_days}', async () => {
    await shareAPI.create(7, 30);
    const c = lastCall();
    expect(c.url).toContain('/api/v1/share-links');
    expect(c.method).toBe('POST');
    expect(c.body).toEqual({ twin_id: 7, expire_days: 30 });
  });

  it('create 不带 expireDays 时 body 只含 twin_id（后端据此算永久链接）', async () => {
    await shareAPI.create(7);
    const c = lastCall();
    expect(c.method).toBe('POST');
    expect(c.body).toEqual({ twin_id: 7 });
    expect(c.body).not.toHaveProperty('expire_days');
  });

  it('list 发 GET /api/v1/share-links', async () => {
    await shareAPI.list();
    const c = lastCall();
    expect(c.url).toContain('/api/v1/share-links');
    expect(c.method).toBe('GET');
    expect(c.body).toBeUndefined();
  });
});
