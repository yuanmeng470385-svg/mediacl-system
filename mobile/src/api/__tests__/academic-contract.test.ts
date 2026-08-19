/**
 * 学术卡片 API 契约测试：锁定 URL/method/body（二期 G）。
 * 参照 qualification-contract 模式 —— 走 client.request（JSON 通道），
 * 断言 fetch 的最后一通调用。
 */
import { academicAPI } from '../academic';

const okResponse = (data: any = {}) => ({
  json: async () => ({ code: 0, message: 'success', data }),
});

let fetchMock: jest.Mock;

beforeEach(() => {
  fetchMock = jest.fn().mockResolvedValue(okResponse());
  (global as any).fetch = fetchMock;
});

function lastCall() {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return { url: url as string, init: init as { method: string; body?: string } };
}

describe('academicAPI', () => {
  it('createCard 发 POST /api/v1/academic-cards', async () => {
    await academicAPI.createCard({ title: '高血压指南', topic: '高血压' });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/academic-cards');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body!)).toEqual({ title: '高血压指南', topic: '高血压' });
  });

  it('listMyCards 发 GET /api/v1/academic-cards', async () => {
    await academicAPI.listMyCards();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/academic-cards');
    expect(init.method).toBe('GET');
  });

  it('pushCard 发 POST /api/v1/academic-cards/1/push', async () => {
    await academicAPI.pushCard(1, [2]);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/academic-cards/1/push');
    expect(JSON.parse(init.body!)).toEqual({ doctor_ids: [2] });
  });
});
