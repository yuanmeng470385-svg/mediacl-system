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

  it('complete 发 POST 且 objections_used 映射为 objectionsUsed（异议话术批 2026-09-10）', async () => {
    fetchMock.mockResolvedValue(okResponse({
      id: 1, status: 'completed',
      scores: { overall: 0.8 },
      objections_used: [
        { content: '医生异议：真实世界数据在哪？', guidance: '引用中国亚组数据' },
        { content: '老年患者用着安全吗？', guidance: null },
      ],
    }));
    const res = await practiceAPI.complete(1);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/practices/1/complete');
    expect(init.method).toBe('POST');
    // 映射后形状（2026-09-04 通知契约同款教训：响应形状也要锁，不只锁请求）
    expect(res.objectionsUsed).toEqual([
      { content: '医生异议：真实世界数据在哪？', guidance: '引用中国亚组数据' },
      { content: '老年患者用着安全吗？', guidance: null },
    ]);
    expect(res.objections_used).toBeUndefined();  // snake_case 不外漏
    expect(res.scores).toEqual({ overall: 0.8 }); // 其余字段原样透传
  });

  it('complete 后端无异议字段时 objectionsUsed 兜底空数组', async () => {
    fetchMock.mockResolvedValue(okResponse({ id: 2, status: 'completed', scores: {} }));
    const res = await practiceAPI.complete(2);
    expect(res.objectionsUsed).toEqual([]);
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

  it('styleSources 发 GET /api/v1/specialists/style-sources', async () => {
    await twinAPI.styleSources();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/specialists/style-sources');
    expect(init.method).toBe('GET');
  });

  it('styleFromRecords 发 POST /api/v1/specialists/style-from-records（sources 进 body）', async () => {
    await twinAPI.styleFromRecords([
      { type: 'visit', id: 1 }, { type: 'chat', id: 'sess-a' },
    ]);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/specialists/style-from-records');
    expect(JSON.parse(init.body)).toEqual({
      sources: [{ type: 'visit', id: 1 }, { type: 'chat', id: 'sess-a' }],
    });
  });

  it('styleFromRecords 带 name 时一并进 body', async () => {
    await twinAPI.styleFromRecords([{ type: 'practice', id: 3 }], '我的专属分身');
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/specialists/style-from-records');
    expect(JSON.parse(init.body)).toEqual({
      sources: [{ type: 'practice', id: 3 }], name: '我的专属分身',
    });
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

  it('releaseSkill 携带 source_visit_ids 时进 body（溯源扩拜访 2026-09-10）', async () => {
    await plazaAPI.releaseSkill({
      name: '严谨型', description: '心内科', content: '话术素材',
      skill_weights: { formal_level: '标准学术' },
      source_visit_ids: [3],
    });
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/release');
    expect(JSON.parse(init.body).source_visit_ids).toEqual([3]);
  });

  it('extractDraft 混合素材时 session_ids + visit_ids 同进 body（2026-09-10 扩拜访）', async () => {
    await plazaAPI.extractDraft([1], [5, 6]);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/extract-draft');
    expect(JSON.parse(init.body)).toEqual({ session_ids: [1], visit_ids: [5, 6] });
  });

  it('extractDraft 未选拜访时 body 不带 visit_ids（旧调用契约不变）', async () => {
    await plazaAPI.extractDraft([101, 102]);
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/extract-draft');
    expect(JSON.parse(init.body)).toEqual({ session_ids: [101, 102] });
  });

  it('mySkills 发 GET /api/v1/skill-packages/mine', async () => {
    await plazaAPI.mySkills();
    const { url, init } = lastCall();
    expect(url).toContain('/api/v1/skill-packages/mine');
    expect(init.method).toBe('GET');
  });
});
