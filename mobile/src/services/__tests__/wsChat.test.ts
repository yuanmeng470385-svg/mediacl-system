import { openChatWs } from '../wsChat';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((e: any) => void) | null = null;
  sent: any[] = [];
  readyState = 0;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    // 模拟连接已建立（真实 WS 打开后 readyState 为 OPEN），否则实现里
    // readyState === WebSocket.OPEN 的守卫不会放行 sendQuestion()
    this.readyState = 1;
  }
  send(data: any) { this.sent.push(data); }
  // 模拟真实 WebSocket.close()：只改状态，不产生任何服务端帧
  close() { this.readyState = 3; }
  // 测试辅助：模拟服务端消息
  emit(data: any) { this.onmessage?.({ data }); }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  (global as any).WebSocket = MockWebSocket;
});

describe('wsChat 客户端', () => {
  it('URL 走网关并带 token 与 specialistId', async () => {
    const ws = openChatWs(3, 'tok-1', { onStart: () => {}, onDelta: () => {}, onDone: () => {}, onError: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    expect(inst.url).toContain(':8000/api/v1/specialists/3/chat/ws');
    expect(inst.url).toContain('token=tok-1');
    ws.close();
  });

  it('sendQuestion 发 question 帧', async () => {
    const ws = openChatWs(3, 'tok', { onStart: () => {}, onDelta: () => {}, onDone: () => {}, onError: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    ws.sendQuestion('你好', 'sess-1');
    expect(inst.sent[0]).toBe(JSON.stringify({ type: 'question', text: '你好', session_id: 'sess-1' }));
    ws.close();
  });

  it('start/delta/done 帧触发回调，done 带 conversationId', async () => {
    const events: string[] = [];
    let convId: number | null | undefined;
    const ws = openChatWs(3, 'tok', {
      onStart: () => events.push('start'),
      onDelta: (t) => events.push('d:' + t),
      onDone: (d) => { events.push('done'); convId = d.conversationId; },
      onError: () => events.push('err'),
    });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    inst.emit(JSON.stringify({ type: 'start' }));
    inst.emit(JSON.stringify({ type: 'delta', text: '你' }));
    inst.emit(JSON.stringify({ type: 'done', text: '你好', conversation_id: 42 }));
    await new Promise((r) => setTimeout(r, 0));
    expect(events).toEqual(['start', 'd:你', 'done']);
    expect(convId).toBe(42);
    ws.close();
  });

  it('error 帧触发 onError', async () => {
    const errors: string[] = [];
    const ws = openChatWs(3, 'tok', { onStart: () => {}, onDelta: () => {}, onDone: () => {}, onError: (m) => errors.push(m) });
    await new Promise((r) => setTimeout(r, 0));
    MockWebSocket.instances[0].emit(JSON.stringify({ type: 'error', message: '生成失败' }));
    await new Promise((r) => setTimeout(r, 0));
    expect(errors).toEqual(['生成失败']);
    ws.close();
  });
});
