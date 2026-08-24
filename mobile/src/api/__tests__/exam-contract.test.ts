/**
 * 合规培训考试 API 契约测试：锁定 URL/method/body JSON 序列化形状。
 * apiClient.request 对 POST 的 body 直接 JSON.stringify 对象，
 * 断言 JSON.parse(init.body) 即拿回原始对象。
 */
import { examAPI } from '../exam';

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
  return { url: url as string, init: init as { method: string; headers: Record<string, string>; body?: any } };
}

describe('examAPI', () => {
  it('listMaterials 发 GET /api/v1/training-materials', async () => {
    await examAPI.listMaterials();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/training-materials');
    expect(init.method).toBe('GET');
  });

  it('startExam 发 POST /api/v1/exams/start 带 question_count', async () => {
    await examAPI.startExam(5);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/exams/start');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ question_count: 5 });
  });

  it('submitExam 发 POST /api/v1/exams/submit 带 session_token + answers', async () => {
    await examAPI.submitExam([{ question_id: 1, selected: [0] }], 'sess-token-1');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/exams/submit');
    expect(JSON.parse(init.body)).toEqual({
      session_token: 'sess-token-1',
      answers: [{ question_id: 1, selected: [0] }],
    });
  });

  it('signCommitment 发 POST /api/v1/qualifications/commitment/sign 带 code', async () => {
    await examAPI.signCommitment('123456');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/qualifications/commitment/sign');
    expect(JSON.parse(init.body)).toEqual({ code: '123456' });
  });
});
