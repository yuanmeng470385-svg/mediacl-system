/**
 * 产品使用 AI 助手 API 契约测试（2026-09-15，照 auth-contract 模式）：
 * 锁定 URL / method / body，mock global.fetch 断言最后一通调用。
 */
import { assistantAPI } from '../assistant';

const okResponse = (data: any = {}) => ({ json: async () => ({ code: 0, message: 'success', data }) });
let fetchMock: jest.Mock;
beforeEach(() => { fetchMock = jest.fn().mockResolvedValue(okResponse()); (global as any).fetch = fetchMock; });
function lastCall() { const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]; return { url, init }; }

describe('assistant API（医生端）', () => {
  it('ask 发 POST /api/v1/assistant/qa（question 进 body）', async () => {
    fetchMock.mockResolvedValue(okResponse({ answer: '在「我的 → 我的分身」里添加。', disclaimer: '以上为产品使用指引，由 AI 生成。' }));
    const res = await assistantAPI.ask('怎么添加代表的数字分身？');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/assistant/qa');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ question: '怎么添加代表的数字分身？' });
    expect(res.answer).toContain('我的分身');
    expect(res.disclaimer).toBeTruthy();
  });
});
