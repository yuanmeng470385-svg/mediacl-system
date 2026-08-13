/**
 * API 契约测试：锁定每个方法实际发出的 URL / method / body 形状。
 * 这一类 bug（路径漂移、camelCase 与 snake_case 错配）编译器抓不到，
 * 2026-08-05 审计一次性发现了 7 处。
 */
import { visitAPI, mapComplianceViolations, mapTranscriptResult } from '../visit';
import { specialistAPI } from '../specialist';
import { complianceAPI } from '../compliance';
import { hcpAPI } from '../hcp';
import { contentAPI, mapDocType } from '../content';
import { authAPI } from '../auth';

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

  it('list 日期参数必须是 date_from / date_to（date_to 带 T23:59:59 覆盖全天，J1）', async () => {
    // 后端 visit_repo 把 date_to 解析为当日 00:00:00 做 <= 过滤，纯日期会使今日拜访恒空；
    // 移动端契约：date_to 必须是 `${date}T23:59:59`（URLSearchParams 编码冒号为 %3A）
    await visitAPI.list({ page: 1, date_from: '2026-08-05', date_to: '2026-08-05T23:59:59' });
    const c = lastCall();
    expect(c.url).toContain('date_from=2026-08-05');
    expect(c.url).toContain('date_to=2026-08-05T23%3A59%3A59');
    expect(c.url).not.toContain('start_date');
  });

  it('getById 发 GET /api/v1/visits/{id}（详情页数据源）', async () => {
    await visitAPI.getById(123);
    const c = lastCall();
    expect(c.url).toContain('/api/v1/visits/123');
    expect(c.method).toBe('GET');
  });

  it('startVisit 取 visit_id，后端只有 id 时回退 id（C1：visitId 不能再是 undefined）', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ id: 55, status: 'in_progress', visit_time: '2026-08-06T10:00:00' }));
    const result = await visitAPI.startVisit({ hcp_id: 1, product_id: 1 });
    expect(result.visit_id).toBe(55);

    // 后端新契约 {id, visit_id, status, start_time}
    fetchMock.mockResolvedValueOnce(okResponse({ id: 55, visit_id: 88, status: 'in_progress', start_time: '2026-08-06T10:00:00' }));
    const result2 = await visitAPI.startVisit({ hcp_id: 1, product_id: 1 });
    expect(result2.visit_id).toBe(88);
  });

  it('startVisit 请求体只发 hcp_id/product_id，不发 planned_date/notes（J4：后端无对应列静默丢弃）', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ id: 77, status: 'in_progress' }));
    await visitAPI.startVisit({ hcp_id: 1, product_id: 2 });
    const c = lastCall();
    expect(c.body).toEqual({ hcp_id: 1, product_id: 2 });
    expect(c.body).not.toHaveProperty('planned_date');
    expect(c.body).not.toHaveProperty('notes');
  });

  it('sendTranscript 把 compliance.violations / objections.objections 映射为屏幕形状（C3）', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({
      visit_id: 1,
      transcript: '主任您好',
      compliance: {
        blocked: true,
        violations: [
          { rule_code: 'R001', rule_name: '禁止承诺疗效', severity: 'high', action: 'reject', matched_text: '保证治愈', reason: '承诺疗效' },
          { rule_code: 'R007', rule_name: '禁止讨论未公开数据', severity: 'high', action: 'warn', matched_text: '' },
        ],
      },
      objections: {
        objections: [{ type: 'price', text: '价格太贵了' }],
        interests: [],
        sentiment: 'neutral',
        method: 'rules',
      },
      suggestions: { objection_responses: [{ objection: '价格太贵了', response: '回应价格异议：引用经济性数据' }] },
    }));
    const r = await visitAPI.sendTranscript(1, { text: '主任您好' });
    expect(r.compliance_alerts).toEqual([
      { rule_code: 'R001', description: '保证治愈', severity: 'high', critical: true },
      { rule_code: 'R007', description: '禁止讨论未公开数据', severity: 'high', critical: false },
    ]);
    expect(r.objections[0]).toMatchObject({
      type: 'price',
      text: '价格太贵了',
      description: '价格太贵了',
      suggested_response: '回应价格异议：引用经济性数据',
    });
  });

  it('mapComplianceViolations：ASR WS compliance 帧与 REST transcript 共用同一告警形状', () => {
    expect(mapComplianceViolations([{ rule_code: 'R002', action: 'reject', matched_text: '回扣' }])).toEqual([
      { rule_code: 'R002', description: '回扣', severity: undefined, critical: true },
    ]);
    expect(mapComplianceViolations('not-an-array')).toEqual([]);
  });

  it('endVisit 把 record.to_dict() 映射为 VisitSummary（ai_summary 字符串包成 summary）', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({
      id: 1,
      status: 'completed',
      ai_summary: '本次拜访达成共识，医生认可安全性',
      key_points: ['关键点1'],
      hcp_interests: ['临床数据'],
      hcp_objections: ['价格负担'],
      follow_up_suggestions: ['发资料'],
      sentiment: 'positive',
      next_visit_plan: { recommended_time: '2026-08-20', recommended_topics: ['药物经济学'], materials_to_send: ['对比资料'] },
      duration_minutes: 30,
    }));
    const r = await visitAPI.endVisit(1);
    expect(r.summary).toBe('本次拜访达成共识，医生认可安全性');
    expect(r.key_points).toEqual(['关键点1']);
    expect(r.interests).toEqual(['临床数据']);
    expect(r.objections).toEqual(['价格负担']);
    expect(r.sentiment).toBe('positive');
    expect(r.next_visit_recommendation).toContain('2026-08-20');
    expect(r.next_visit_recommendation).toContain('药物经济学');
  });

  it('endVisit 对 ai_summary 为 JSON 字符串时解析出结构化字段', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({
      id: 1,
      status: 'completed',
      ai_summary: '{"summary":"s1","key_points":["k1"],"hcp_interests":["i1"],"hcp_objections":["o1"]}',
      sentiment: 'neutral',
      next_visit_plan: {},
    }));
    const r = await visitAPI.endVisit(1);
    expect(r.summary).toBe('s1');
    expect(r.key_points).toEqual(['k1']);
    expect(r.interests).toEqual(['i1']);
    expect(r.objections).toEqual(['o1']);
  });

  it('followUp 解析 follow_up AI JSON 为 follow_up_plan / suggested_date（C4）', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({
      visit_id: 1,
      follow_up: {
        follow_up_items: [
          { action: '发送产品资料', due: '2026-08-20', channel: '微信' },
          { action: '预约下次拜访', due: '', channel: '下次拜访' },
        ],
        reminders: ['带上对比资料'],
      },
      degraded: false,
    }));
    const r = await visitAPI.followUp(1);
    expect(r.follow_up_plan).toContain('发送产品资料（2026-08-20）');
    expect(r.follow_up_plan).toContain('带上对比资料');
    expect(r.suggested_date).toBe('2026-08-20');
  });

  it('followUp 解析失败返回空结构，不崩', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ visit_id: 1, follow_up: '不是JSON', degraded: true }));
    const r = await visitAPI.followUp(1);
    expect(r).toEqual({ follow_up_plan: '', suggested_date: '' });
  });

  it('list 解包 pagination 嵌套并映射 items（hcp_name / planned_date / ai_summary）', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({
      items: [
        { id: 9, hcp_id: 3, hcp_name: '张主任', visit_time: '2026-08-06T09:30:00', duration_minutes: 25, status: 'completed', ai_summary: '不错' },
        { id: 10, hcp_id: 4, visit_time: '2026-08-06T10:00:00', status: 'in_progress', ai_summary: null },
      ],
      pagination: { page: 1, page_size: 20, total: 42 },
    }));
    const r = await visitAPI.list({ page: 1 });
    expect(r.total).toBe(42);
    expect(r.items.length).toBe(2);
    expect(r.items[0].hcp_name).toBe('张主任');
    expect(r.items[0].planned_date).toBe('2026-08-06');
    expect(r.items[0].ai_summary?.summary).toBe('不错');
    expect(r.items[0].actual_end_time).toBeTruthy();
    expect(r.items[1].hcp_name).toBe('医生 #4');
    expect(r.items[1].status).toBe('in_progress');
  });

  it('getById 映射记录，hcp_name 缺省回退 医生 #id', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ id: 9, hcp_id: 3, visit_time: '2026-08-06T09:30:00', status: 'completed', ai_summary: null }));
    const r = await visitAPI.getById(9);
    expect(r.hcp_name).toBe('医生 #3');
    expect(r.planned_date).toBe('2026-08-06');
    expect(r.ai_summary).toBeUndefined();
  });

  it('J3：AI 失败占位串不推 completed——status 保持 in_progress、ai_summary 为 undefined、retryable=true', async () => {
    const placeholder = '（AI 总结生成失败，拜访尚未结束，可重试结束拜访）';
    fetchMock.mockResolvedValueOnce(okResponse({
      items: [
        { id: 11, hcp_id: 3, hcp_name: '张主任', visit_time: '2026-08-06T09:30:00', status: 'in_progress', ai_summary: placeholder },
      ],
      pagination: { page: 1, page_size: 20, total: 1 },
    }));
    const r = await visitAPI.list({ page: 1 });
    expect(r.items[0].status).toBe('in_progress');
    expect(r.items[0].ai_summary).toBeUndefined();
    expect(r.items[0].retryable).toBe(true);
  });

  it('J3：endVisit 返回占位串 → retryable=true 且 summary 为空（不把占位串当总结展示）', async () => {
    const placeholder = '（AI 总结生成失败，拜访尚未结束，可重试结束拜访）';
    fetchMock.mockResolvedValueOnce(okResponse({ id: 1, status: 'in_progress', ai_summary: placeholder }));
    const r = await visitAPI.endVisit(1);
    expect(r.retryable).toBe(true);
    expect(r.summary).toBe('');
  });

  it('mapTranscriptResult 解析 LLM 推荐字段（key_nodes/ai_suggestion）', () => {
    const result = mapTranscriptResult({
      transcript: '主任表示考虑使用',
      objections: { objections: [] },
      compliance: { violations: [] },
      key_nodes: [
        { type: 'decision_point', label: '决策表态', quote: '主任表示考虑使用' },
        { type: 'unknown_type', label: '忽略', quote: '' },
      ],
      ai_suggestion: { topic: '价格', advice: '建议强调药物经济学优势' },
    });
    expect(result.key_nodes).toHaveLength(1);
    expect(result.key_nodes[0]).toMatchObject({ type: 'decision_point', label: '决策表态' });
    expect(result.ai_suggestion).toEqual({ topic: '价格', advice: '建议强调药物经济学优势' });
  });

  it('mapTranscriptResult 缺推荐字段时容错为空', () => {
    const result = mapTranscriptResult({ transcript: 'x', objections: [], compliance: { violations: [] } });
    expect(result.key_nodes).toEqual([]);
    expect(result.ai_suggestion).toBeNull();
  });

  it('prepareVisit 把平铺 hcp_profile 包成 basic_info、recommendations 兼容中文键', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({
      hcp_profile: { id: 7, name: '李主任', hospital: '市一院', department: '心内科', title: '主任医师', region: '华东' },
      recommendations: {
        '推荐话题': ['临床数据更新', '患者管理'],
        '红线提醒': ['不得承诺疗效', '不得贬低竞品'],
        '开场白建议': '主任您好，感谢您抽出时间。',
        '上次未完成的跟进项': '发送 III 期临床资料',
        '材料清单': ['产品手册', '文献汇编'],
      },
      degraded: false,
    }));
    const r = await visitAPI.prepareVisit({ hcpId: 7, productId: 1 });
    expect(r.hcp_profile.basic_info).toEqual({ name: '李主任', hospital: '市一院', department: '心内科', title: '主任医师', region: '华东' });
    expect(r.recommendations.suggested_topics).toEqual(['临床数据更新', '患者管理']);
    expect(r.recommendations.red_lines).toEqual(['不得承诺疗效', '不得贬低竞品']);
    expect(r.recommendations.opening_remarks).toBe('主任您好，感谢您抽出时间。');
    expect(r.recommendations.last_follow_up).toBe('发送 III 期临床资料');
    expect(r.recommendations.materials.map((m) => m.title)).toEqual(['产品手册', '文献汇编']);
  });

  it('prepareVisit 兼容英文键与 materials 字符串清单', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({
      hcp_profile: { name: '王主任', hospital: '二院', department: '神内', title: '副主任医师' },
      recommendations: {
        suggested_topics: ['指南解读'],
        red_lines: ['红线1'],
        opening_remarks: '开场',
        last_follow_up: '跟进项',
        materials: '产品手册；文献汇编',
      },
    }));
    const r = await visitAPI.prepareVisit({ hcpId: 8, productId: 1 });
    expect(r.recommendations.suggested_topics).toEqual(['指南解读']);
    expect(r.recommendations.materials.map((m) => m.title)).toEqual(['产品手册', '文献汇编']);
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

  it('list 解出分页对象里的 items（后端 specialists.py 返回 paginate(...)，非裸数组）', async () => {
    fetchMock.mockResolvedValueOnce({
      json: async () => ({
        code: 0,
        message: 'success',
        data: {
          items: [{ id: 1, name: '肿瘤产品专员-小K', status: 'active' }],
          total: 1,
          page: 1,
          page_size: 20,
        },
      }),
    });
    const result = await specialistAPI.list({ page_size: 50 });
    expect(Array.isArray(result)).toBe(true);
    expect(result[0].name).toBe('肿瘤产品专员-小K');
    expect((result as any).items).toBeUndefined();
  });
});

describe('complianceAPI', () => {
  it('listRules 走 /redlines 净化端点（/rules 含 patterns 已收紧为规则管理员）', async () => {
    await complianceAPI.listRules();
    expect(lastCall().url).toContain('/api/v1/compliance/redlines');
    expect((complianceAPI as any).checkContent).toBeUndefined();
  });

  it('listRules 解出分页对象里的 items（后端 rules.py:110 返回 paginate(...)）', async () => {
    fetchMock.mockResolvedValueOnce({
      json: async () => ({
        code: 0,
        message: 'success',
        data: { items: [{ rule_code: 'R001', severity: 'high' }], total: 1, page: 1, page_size: 20 },
      }),
    });
    const result = await complianceAPI.listRules();
    expect(Array.isArray(result)).toBe(true);
    expect(result[0].rule_code).toBe('R001');
    expect((result as any).items).toBeUndefined();
  });
});

describe('authAPI', () => {
  it('loginByPassword 发 POST /api/v1/auth/login 且 body 为 username+password', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ token: 't-1', user: { id: 1, name: '张三' } }));
    const r = await authAPI.loginByPassword('admin', 'secret');
    const c = lastCall();
    expect(c.url).toContain('/api/v1/auth/login');
    expect(c.method).toBe('POST');
    expect(c.body).toEqual({ username: 'admin', password: 'secret' });
    expect(r.token).toBe('t-1');
    // 登录成功后 token 已存储（与验证码登录共用存储逻辑）
    expect(await authAPI.getToken()).toBe('t-1');
    expect((await authAPI.getCachedUser())?.name).toBe('张三');
  });

  it('login（验证码）body 为 phone+code，token 同样入库', async () => {
    fetchMock.mockResolvedValueOnce(okResponse({ token: 't-2', user: { id: 2, name: '李四' } }));
    await authAPI.login('13800000000', '123456');
    const c = lastCall();
    expect(c.body).toEqual({ phone: '13800000000', code: '123456' });
    expect(await authAPI.getToken()).toBe('t-2');
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

describe('contentAPI', () => {
  it('getDocuments 发 GET /api/v1/knowledge/documents 且透传 doc_type', async () => {
    await contentAPI.getDocuments({ page: 1, page_size: 50, doc_type: 'guideline' });
    const c = lastCall();
    expect(c.url).toContain('/api/v1/knowledge/documents');
    expect(c.url).toContain('doc_type=guideline');
    expect(c.method).toBe('GET');
  });

  it('getDocument 发 GET /api/v1/knowledge/documents/{id}', async () => {
    await contentAPI.getDocument(7);
    const c = lastCall();
    expect(c.url).toContain('/api/v1/knowledge/documents/7');
    expect(c.method).toBe('GET');
  });

  it('mapDocType：后端 doc_type → 前端 type（Tab 过滤恒空的回归）', () => {
    // 后端 6 种枚举（knowledge.py ALLOWED_DOC_TYPES）
    expect(mapDocType('literature')).toBe('literature');
    expect(mapDocType('guideline')).toBe('guideline');
    expect(mapDocType('regulation')).toBe('guideline');
    expect(mapDocType('product')).toBe('manual');
    expect(mapDocType('competitor')).toBe('news');
    expect(mapDocType('other')).toBe('news');
    expect(mapDocType(undefined)).toBe('news');
  });

  it('getDocuments 返回项已做 doc_type→type 映射', async () => {
    fetchMock.mockResolvedValueOnce({
      json: async () => ({
        code: 0,
        message: 'success',
        data: { items: [{ id: 1, title: '某产品说明书', doc_type: 'product' }], total: 1, page: 1, page_size: 50 },
      }),
    });
    const res = await contentAPI.getDocuments({ page: 1 });
    expect(res.items[0].type).toBe('manual');
    expect(res.items[0].title).toBe('某产品说明书');
  });
});
