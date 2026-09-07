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

describe('academicAPI 通知中心（2026-09-03 业务审查批）', () => {
  it('notifications 默认 GET 分页，unreadOnly 带查询参数', async () => {
    await academicAPI.notifications();
    let { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes/notifications?');
    expect(url).toContain('page=1');
    expect(url).toContain('page_size=20');
    expect(url).not.toContain('unread_only');
    expect(init.method).toBe('GET');

    await academicAPI.notifications(2, 10, true);
    ({ url, init } = lastCall());
    expect(url).toContain('page=2');
    expect(url).toContain('unread_only=true');
  });

  it('unreadCount 发 GET /notifications/unread-count', async () => {
    await academicAPI.unreadCount();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes/notifications/unread-count');
    expect(init.method).toBe('GET');
  });

  it('markRead 单条带 notification_id、全部带 all', async () => {
    await academicAPI.markRead(7);
    let { init } = lastCall();
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body!)).toEqual({ notification_id: 7 });

    await academicAPI.markRead(undefined, true);
    ({ init } = lastCall());
    expect(JSON.parse(init.body!)).toEqual({ all: true });
  });

  it('notifications 响应映射 snake_case → isRead/createdAt（2026-09-04 预演暴露错位）', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({
      items: [{
        id: 3, user_id: 9, type: 'briefing_ready', title: '你的夜间简报已生成',
        content: '查看医生提问汇总', link: '/briefings', is_read: false,
        created_at: '2026-09-04T06:00:00',
      }],
      total: 1, page: 1, page_size: 20,
    }));
    const res = await academicAPI.notifications();
    expect(res.items).toEqual([{
      id: 3, type: 'briefing_ready', title: '你的夜间简报已生成',
      content: '查看医生提问汇总', link: '/briefings',
      isRead: false, createdAt: '2026-09-04T06:00:00',
    }]);
    // 屏幕组件只应看到 camelCase 形状
    expect((res.items[0] as any).is_read).toBeUndefined();
    expect((res.items[0] as any).created_at).toBeUndefined();
  });
});

describe('academicAPI pushTargets（2026-09-03 业务审查批）', () => {
  it('pushTargets 发 GET /api/v1/academic-cards/push-targets', async () => {
    await academicAPI.pushTargets();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/academic-cards/push-targets');
    expect(init.method).toBe('GET');
  });
});
