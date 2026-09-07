/**
 * 医生端学术卡片收件箱 API 契约测试：锁定 URL/method/body。
 *   - listInbox: GET /api/v1/card-pushes（收件箱分页，带 card 对象）
 *   - trackRead: POST /api/v1/card-pushes/{id}/track {read_status, seconds}
 *   - submitFeedback: POST /api/v1/card-pushes/{id}/feedback {feedback}
 *   - notifications/unreadCount/markRead: 站内通知消费（2026-09-07 A-1）——
 *     除 URL/body 外还锁映射后响应形状（is_read→isRead 等，防 snake_case 错位复发，
 *     同款教训见代表端 2026-09-07 修复）
 */
import { inboxAPI } from '../inbox';

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
  return {
    url: url as string,
    init: init as { method: string; body?: any },
  };
}

describe('inboxAPI', () => {
  it('listInbox 发 GET /api/v1/card-pushes', async () => {
    await inboxAPI.listInbox();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes');
    expect(init.method).toBe('GET');
  });

  it('trackRead 发 POST /api/v1/card-pushes/1/track', async () => {
    await inboxAPI.trackRead(1, 'read', 42);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes/1/track');
    expect(JSON.parse(init.body)).toEqual({ read_status: 'read', seconds: 42 });
  });

  it('submitFeedback 发 POST /api/v1/card-pushes/1/feedback', async () => {
    await inboxAPI.submitFeedback(1, 'useful');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes/1/feedback');
    expect(JSON.parse(init.body)).toEqual({ feedback: 'useful' });
  });
});

describe('inboxAPI 通知消费（2026-09-07 A-1）', () => {
  it('notifications 发 GET /notifications 且映射 snake_case → isRead/createdAt', async () => {
    fetchMock.mockResolvedValue(okResponse({
      total: 2,
      items: [
        { id: 1, type: 'card_new', title: '新卡片', content: 'c', link: '/card-pushes', is_read: false, created_at: '2026-09-07T02:00:00' },
        { id: 2, type: 'card_new', title: '已读', content: null, link: null, is_read: true, created_at: null },
      ],
    }));
    const res = await inboxAPI.notifications(1, 20);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes/notifications?page=1&page_size=20');
    expect(init.method).toBe('GET');
    expect(res.total).toBe(2);
    expect(res.items[0]).toEqual({
      id: 1, type: 'card_new', title: '新卡片', content: 'c', link: '/card-pushes',
      isRead: false, createdAt: '2026-09-07T02:00:00',
    });
    // 映射后形状不再暴露 snake_case 原始键（红点/时间列依赖 isRead/createdAt）
    expect(res.items[0]).not.toHaveProperty('is_read');
    expect(res.items[0]).not.toHaveProperty('created_at');
    expect(res.items[1].isRead).toBe(true);
    expect(res.items[1].createdAt).toBeNull();
  });

  it('notifications unreadOnly 透传 unread_only=true', async () => {
    fetchMock.mockResolvedValue(okResponse({ total: 0, items: [] }));
    await inboxAPI.notifications(2, 10, true);
    expect(lastCall().url).toContain('unread_only=true');
  });

  it('unreadCount 发 GET /notifications/unread-count', async () => {
    fetchMock.mockResolvedValue(okResponse({ unread: 3 }));
    const res = await inboxAPI.unreadCount();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/card-pushes/notifications/unread-count');
    expect(init.method).toBe('GET');
    expect(res.unread).toBe(3);
  });

  it('markRead 单条发 notification_id、全部发 {all:true}', async () => {
    await inboxAPI.markRead(5);
    expect(lastCall().url).toContain('/api/v1/card-pushes/notifications/read');
    expect(JSON.parse(lastCall().init.body)).toEqual({ notification_id: 5 });

    await inboxAPI.markRead(undefined, true);
    expect(JSON.parse(lastCall().init.body)).toEqual({ all: true });
  });
});
