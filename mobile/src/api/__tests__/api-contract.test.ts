/**
 * API 契约测试：锁定每个方法实际发出的 URL / method / body 形状。
 * 这一类 bug（路径漂移、camelCase 与 snake_case 错配）编译器抓不到，
 * 2026-08-05 审计一次性发现了 7 处。
 */
import { visitAPI } from '../visit';
import { specialistAPI } from '../specialist';
import { complianceAPI } from '../compliance';
import { hcpAPI } from '../hcp';

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

describe('visitAPI', () => {
  it('prepareVisit 必须发 snake_case（后端 visits.py:65 读 hcp_id）', async () => {
    await visitAPI.prepareVisit({ hcpId: 7, productId: 1 });
    const c = lastCall();
    expect(c.url).toContain('/api/v1/visits/pre-visit');
    expect(c.method).toBe('POST');
    expect(c.body).toEqual({ hcp_id: 7, product_id: 1 });
    expect(c.body).not.toHaveProperty('hcpId');
  });

  it('list 日期参数必须是 date_from / date_to', async () => {
    await visitAPI.list({ page: 1, date_from: '2026-08-05', date_to: '2026-08-05' });
    const c = lastCall();
    expect(c.url).toContain('date_from=2026-08-05');
    expect(c.url).toContain('date_to=2026-08-05');
    expect(c.url).not.toContain('start_date');
  });
});

describe('specialistAPI', () => {
  it('sendFeedback 挂 conversation_id，rating 是 1/-1', async () => {
    await specialistAPI.sendFeedback(42, 1, '很有用');
    const c = lastCall();
    expect(c.url).toContain('/api/v1/conversations/42/feedback');
    expect(c.method).toBe('POST');
    expect(c.body).toEqual({ rating: 1, comment: '很有用' });
  });

  it('sendFeedback 不传 comment 时不带该字段', async () => {
    await specialistAPI.sendFeedback(42, -1);
    expect(lastCall().body).toEqual({ rating: -1 });
  });

  it('toggleFavorite 是无 body 的 toggle', async () => {
    await specialistAPI.toggleFavorite(42);
    const c = lastCall();
    expect(c.url).toContain('/api/v1/conversations/42/favorite');
    expect(c.method).toBe('POST');
    expect(c.body).toBeUndefined();
  });

  it('会话历史走 specialists 前缀', async () => {
    await specialistAPI.getConversationHistory('sess-1');
    const c = lastCall();
    expect(c.url).toContain('/api/v1/specialists/conversations/sess-1');
    expect(c.method).toBe('GET');
  });

  it('chat 路径与 body 不变', async () => {
    await specialistAPI.sendMessage(1, { question: '你好' });
    const c = lastCall();
    expect(c.url).toContain('/api/v1/specialists/1/chat');
    expect(c.body).toEqual({ question: '你好' });
  });
});

describe('complianceAPI', () => {
  it('只保留 listRules（checkContent 已删：网关 INTERNAL_PATHS 恒 403）', async () => {
    await complianceAPI.listRules();
    expect(lastCall().url).toContain('/api/v1/compliance/rules');
    expect((complianceAPI as any).checkContent).toBeUndefined();
  });
});

describe('hcpAPI', () => {
  it('list 透传筛选参数', async () => {
    await hcpAPI.list({ page: 1, name: '张' });
    const c = lastCall();
    expect(c.url).toContain('/api/v1/hcps');
    expect(c.url).toContain('name=');
  });
});
