import { connectAsr } from '../asr';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((e: any) => void) | null = null;
  onclose: (() => void) | null = null;
  sent: any[] = [];
  readyState = 0;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    // 模拟连接已建立（真实 WS 打开后 readyState 为 OPEN），否则实现里
    // readyState === WebSocket.OPEN 的守卫不会放行 stop()/sendAudioChunk()
    this.readyState = 1;
  }
  send(data: any) { this.sent.push(data); }
  close() { this.readyState = 3; this.onclose?.(); }
  // 测试辅助：模拟服务端消息
  emit(data: any) { this.onmessage?.({ data }); }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  (global as any).WebSocket = MockWebSocket;
});

describe('asr 客户端', () => {
  it('连接 URL 带 token 与 visitId', async () => {
    const ws = connectAsr(5, 'jwt-token-abc', { onReady: () => {}, onSentence: () => {}, onCompliance: () => {}, onError: () => {}, onCompleted: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    expect(inst.url).toContain('/ws/visits/5/asr');
    expect(inst.url).toContain('token=jwt-token-abc');
    ws.close();
  });

  it('sentence 帧解析后回调', async () => {
    const sentences: Array<[string, boolean]> = [];
    const ws = connectAsr(5, 'tok', { onReady: () => {}, onSentence: (t, f) => sentences.push([t, f]), onCompliance: () => {}, onError: () => {}, onCompleted: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    inst.emit(JSON.stringify({ type: 'sentence', index: 0, text: '你好', final: false }));
    inst.emit(JSON.stringify({ type: 'sentence', index: 1, text: '医生', final: true }));
    await new Promise((r) => setTimeout(r, 0));
    expect(sentences).toEqual([['你好', false], ['医生', true]]);
    ws.close();
  });

  it('error 帧回调 onError（NLS 未配置场景）', async () => {
    const errors: string[] = [];
    const ws = connectAsr(5, 'tok', { onReady: () => {}, onSentence: () => {}, onCompliance: () => {}, onError: (m) => errors.push(m), onCompleted: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    MockWebSocket.instances[0].emit(JSON.stringify({ type: 'error', message: 'NLS 未配置' }));
    await new Promise((r) => setTimeout(r, 0));
    expect(errors).toEqual(['NLS 未配置']);
    ws.close();
  });

  it('stop() 发送 {"type":"stop"}', async () => {
    const ws = connectAsr(5, 'tok', { onReady: () => {}, onSentence: () => {}, onCompliance: () => {}, onError: () => {}, onCompleted: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    ws.stop();
    expect(inst.sent[inst.sent.length - 1]).toBe(JSON.stringify({ type: 'stop' }));
    ws.close();
  });

  it('completed 帧回调 onCompleted 并关闭连接', async () => {
    let done = false;
    const ws = connectAsr(5, 'tok', { onReady: () => {}, onSentence: () => {}, onCompliance: () => {}, onError: () => {}, onCompleted: () => { done = true; } });
    await new Promise((r) => setTimeout(r, 0));
    MockWebSocket.instances[0].emit(JSON.stringify({ type: 'completed' }));
    await new Promise((r) => setTimeout(r, 0));
    expect(done).toBe(true);
  });
});
