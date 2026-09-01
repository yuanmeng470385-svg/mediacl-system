/**
 * AI 陪练 / Skill 广场 / 分身管理 API 契约测试（二期 H）：
 * 锁定 URL / method / body（走 client.request 的 JSON 通道），断言 fetch 最后一通调用。
 */
import { practiceAPI, plazaAPI, twinAPI } from '../practice';

const okResponse = (data: any = {}) => ({ json: async () => ({ code: 0, message: 'success', data }) });
let fetchMock: jest.Mock;
beforeEach(() => { fetchMock = jest.fn().mockResolvedValue(okResponse()); (global as any).fetch = fetchMock; });
function lastCall() { const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]; return { url, init }; }

describe('practice/plaza/twin API', () => {
  it('createPractice 发 POST /api/v1/practices', async () => {
    await practiceAPI.create({ skill_id: 1, scenario: '心内科推广' });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/practices');
    expect(JSON.parse(init.body)).toEqual({ skill_id: 1, scenario: '心内科推广' });
  });

  it('practiceTurn 发 POST /api/v1/practices/1/turn', async () => {
    await practiceAPI.turn(1, '您好');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/practices/1/turn');
    expect(JSON.parse(init.body)).toEqual({ message: '您好' });
  });

  it('plazaList 发 GET /api/v1/skill-packages/public', async () => {
    await plazaAPI.list();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/public');
    expect(init.method).toBe('GET');
  });

  it('setStyle 发 PUT /api/v1/specialists/1/style', async () => {
    await twinAPI.setStyle(1, { formal_level: '标准学术' });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/specialists/1/style');
    expect(init.method).toBe('PUT');
  });

  it('styleTest 发 POST /api/v1/specialists/style-test', async () => {
    await twinAPI.styleTest([1, 2, 0, 1, 2]);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/specialists/style-test');
    expect(JSON.parse(init.body)).toEqual({ answers: [1, 2, 0, 1, 2] });
  });

  it('releaseSkill 发 POST /api/v1/skill-packages/release', async () => {
    await plazaAPI.releaseSkill({
      name: '亲和力型', description: '心内科', content: '话术素材',
      style_tags: ['亲和力'], skill_weights: { formal_level: '标准学术' }, is_anonymous: true,
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/release');
    expect(JSON.parse(init.body)).toEqual({
      name: '亲和力型', description: '心内科', content: '话术素材',
      style_tags: ['亲和力'], skill_weights: { formal_level: '标准学术' }, is_anonymous: true,
    });
  });

  it('releaseSkill 携带 source_session_ids 时进 body（审核溯源 2026-09-01）', async () => {
    await plazaAPI.releaseSkill({
      name: '严谨型', description: '心内科', content: '话术素材',
      skill_weights: { formal_level: '标准学术' },
      source_session_ids: [7, 5],
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/release');
    const body = JSON.parse(init.body);
    expect(body.source_session_ids).toEqual([7, 5]);
  });

  it('mySkills 发 GET /api/v1/skill-packages/mine', async () => {
    await plazaAPI.mySkills();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/mine');
    expect(init.method).toBe('GET');
  });
});
