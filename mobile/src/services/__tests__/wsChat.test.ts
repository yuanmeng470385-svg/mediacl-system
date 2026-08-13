import { openChatWs } from '../wsChat';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CONNECTING = 0;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((e: any) => void) | null = null;
  onclose: ((e?: any) => void) | null = null;
  onerror: ((e?: any) => void) | null = null;
  sent: any[] = [];
  // 与真实 RN WebSocket 一致：构造时为 CONNECTING(0)，onopen 后才进入 OPEN(1)
  readyState = 0;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  send(data: any) { this.sent.push(data); }
  // 模拟真实 WebSocket.close()：只改状态，不产生任何服务端帧
  close() { this.readyState = 3; }
  // 测试辅助：模拟连接建立（readyState → OPEN 并触发 onopen）
  triggerOpen() {
    this.readyState = 1;
    this.onopen?.();
  }
  // 测试辅助：模拟服务端/网络断开（只触发 onclose）
  simulateClose() {
    this.onclose?.({});
  }
  // 测试辅助：模拟网络层 onerror（触发后可能不再有 onclose，见实现修复）
  simulateError() {
    this.onerror?.({});
  }
  // 测试辅助：模拟服务端消息
  emit(data: any) { this.onmessage?.({ data }); }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  (global as any).WebSocket = MockWebSocket;
});

const noopCbs = { onStart: () => {}, onDelta: () => {}, onDone: () => {}, onError: () => {} };

describe('wsChat 客户端', () => {
  it('URL 走网关且不含 token（B5：token 移出 query，改首帧 auth）', () => {
    const ws = openChatWs(3, 'tok-1', noopCbs);
    const inst = MockWebSocket.instances[0];
    expect(inst.url).toContain(':8000/api/v1/specialists/3/chat/ws');
    expect(inst.url).not.toContain('token=');
    ws.close();
  });

  it('onopen 首帧发 auth 帧，再发 question 帧（open 后）', () => {
    const ws = openChatWs(3, 'tok', noopCbs);
    const inst = MockWebSocket.instances[0];
    inst.triggerOpen();
    ws.sendQuestion('你好', 'sess-1');
    expect(inst.sent[0]).toBe(JSON.stringify({ type: 'auth', token: 'tok' }));
    expect(inst.sent[1]).toBe(JSON.stringify({ type: 'question', text: '你好', session_id: 'sess-1' }));
    ws.close();
  });

  it('open 前 sendQuestion 先缓冲，open 后 auth 帧 + question 帧顺序补发', () => {
    const ws = openChatWs(3, 'tok', noopCbs);
    const inst = MockWebSocket.instances[0];
    expect(inst.readyState).toBe(0);                 // 真实时序：构造后仍是 CONNECTING
    ws.sendQuestion('你好', 'sess-1');
    expect(inst.sent).toHaveLength(0);               // 未 open 不发送
    inst.triggerOpen();
    expect(inst.sent[0]).toBe(JSON.stringify({ type: 'auth', token: 'tok' }));
    expect(inst.sent[1]).toBe(JSON.stringify({ type: 'question', text: '你好', session_id: 'sess-1' }));
    ws.close();
  });

  it('open 前 close 丢弃缓冲的 question，不再补发（auth 帧仍由 onopen 发）', () => {
    const ws = openChatWs(3, 'tok', noopCbs);
    const inst = MockWebSocket.instances[0];
    ws.sendQuestion('你好');
    ws.close();
    inst.triggerOpen();
    expect(inst.sent).toEqual([JSON.stringify({ type: 'auth', token: 'tok' })]);
  });

  it('start/delta/done 帧触发回调，done 带 conversationId', () => {
    const events: string[] = [];
    let convId: number | null | undefined;
    const ws = openChatWs(3, 'tok', {
      onStart: () => events.push('start'),
      onDelta: (t) => events.push('d:' + t),
      onDone: (d) => { events.push('done'); convId = d.conversationId; },
      onError: () => events.push('err'),
    });
    const inst = MockWebSocket.instances[0];
    inst.emit(JSON.stringify({ type: 'start' }));
    inst.emit(JSON.stringify({ type: 'delta', text: '你' }));
    inst.emit(JSON.stringify({ type: 'done', text: '你好', conversation_id: 42 }));
    expect(events).toEqual(['start', 'd:你', 'done']);
    expect(convId).toBe(42);
    ws.close();
  });

  it('done 帧透传 blocked/violations/evidenceLevel', () => {
    let got: any;
    const ws = openChatWs(3, 'tok', { ...noopCbs, onDone: (d) => { got = d; } });
    const inst = MockWebSocket.instances[0];
    inst.emit(JSON.stringify({
      type: 'done',
      text: '该问题涉及不合规内容',
      conversation_id: 7,
      blocked: true,
      violations: [{ description: '违规一' }, { description: '违规二' }],
      evidence_level: 'D',
    }));
    expect(got).toMatchObject({
      text: '该问题涉及不合规内容',
      conversationId: 7,
      blocked: true,
      violations: [{ description: '违规一' }, { description: '违规二' }],
      evidenceLevel: 'D',
    });
    ws.close();
  });

  it('error 帧触发 onError', () => {
    const errors: string[] = [];
    const ws = openChatWs(3, 'tok', { ...noopCbs, onError: (m) => errors.push(m) });
    MockWebSocket.instances[0].emit(JSON.stringify({ type: 'error', message: '生成失败' }));
    expect(errors).toEqual(['生成失败']);
    ws.close();
  });

  it('onerror 主动 close 释放连接（否则不保证 onclose），且不重复上报', () => {
    const errors: string[] = [];
    const ws = openChatWs(3, 'tok', { ...noopCbs, onError: (m) => errors.push(m) });
    const inst = MockWebSocket.instances[0];
    inst.simulateError();
    expect(errors).toEqual(['对话服务连接失败']);
    // 修复点：onerror 后主动 close → readyState 进入 CLOSED，连接真正释放
    expect(inst.readyState).toBe(3);
    // 即使随后 onclose 到达，done 已置位也不重复上报
    inst.simulateClose();
    expect(errors).toEqual(['对话服务连接失败']);
    ws.close();
  });

  it('意外断开触发 onError；主动 close / done / error 后的断开不上报', () => {
    const errors: string[] = [];
    const mk = () => openChatWs(3, 'tok', { ...noopCbs, onError: (m) => errors.push(m) });
    const inst = (i: number) => MockWebSocket.instances[i];

    // 1) 未按协议结束即断开 → 故障上报
    const ws1 = mk();
    inst(0).simulateClose();
    expect(errors).toEqual(['对话连接已断开']);

    // 2) 主动 close 后再断开 → 不上报
    ws1.close();
    inst(0).simulateClose();
    expect(errors).toEqual(['对话连接已断开']);

    // 3) done 帧正常结束后断开 → 不上报
    const ws2 = mk();
    inst(1).emit(JSON.stringify({ type: 'done', text: 'ok' }));
    inst(1).simulateClose();
    expect(errors).toEqual(['对话连接已断开']);

    // 4) error 帧结束后断开 → 不上报
    const ws3 = mk();
    inst(2).emit(JSON.stringify({ type: 'error', message: '生成失败' }));
    inst(2).simulateClose();
    expect(errors).toEqual(['对话连接已断开', '生成失败']);
    ws2.close();
    ws3.close();
  });
});
