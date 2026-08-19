/**
 * 医生端学术卡片收件箱 API 契约测试：锁定 URL/method/body。
 *   - listInbox: GET /api/v1/card-pushes（收件箱分页，带 card 对象）
 *   - trackRead: POST /api/v1/card-pushes/{id}/track {read_status, seconds}
 *   - submitFeedback: POST /api/v1/card-pushes/{id}/feedback {feedback}
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
