/**
 * 产品使用 AI 助手 API 契约测试（2026-09-15）：
 * 锁定 URL / method / body，断言 fetch 最后一通调用。
 */
import { assistantAPI } from '../assistant';

const okResponse = (data: any = {}) => ({ json: async () => ({ code: 0, message: 'success', data }) });
let fetchMock: jest.Mock;
beforeEach(() => { fetchMock = jest.fn().mockResolvedValue(okResponse()); (global as any).fetch = fetchMock; });
function lastCall() { const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]; return { url, init }; }

describe('assistant API', () => {
  it('ask 发 POST /api/v1/assistant/qa（question 进 body）', async () => {
    fetchMock.mockResolvedValue(okResponse({ answer: '在「我的 → 分身管理」。', disclaimer: '以上为产品使用指引，由 AI 生成。' }));
    const res = await assistantAPI.ask('在哪里管理我的数字分身？');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/assistant/qa');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ question: '在哪里管理我的数字分身？' });
    // 响应形状（snake_case 无需映射：answer/disclaimer 两键后端即驼峰安全词）
    expect(res.answer).toContain('分身管理');
    expect(res.disclaimer).toBeTruthy();
  });
});
