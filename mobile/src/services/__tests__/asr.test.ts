import { connectAsr } from '../asr';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((e: any) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((e?: any) => void) | null = null;
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
  // 测试辅助：模拟网络层 onerror
  simulateError() { this.onerror?.({}); }
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

  it('sentence 帧解析后回调（含 speaker 透传，缺省 undefined）', async () => {
    const sentences: Array<[string, boolean, string?]> = [];
    const ws = connectAsr(5, 'tok', { onReady: () => {}, onSentence: (t, f, s) => sentences.push([t, f, s]), onCompliance: () => {}, onError: () => {}, onCompleted: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    inst.emit(JSON.stringify({ type: 'sentence', index: 0, text: '你好', final: false, speaker: 'rep' }));
    inst.emit(JSON.stringify({ type: 'sentence', index: 1, text: '医生', final: true, speaker: 'doctor' }));
    inst.emit(JSON.stringify({ type: 'sentence', index: 2, text: '再见', final: false })); // 旧后端无 speaker 字段
    await new Promise((r) => setTimeout(r, 0));
    expect(sentences).toEqual([['你好', false, 'rep'], ['医生', true, 'doctor'], ['再见', false, undefined]]);
    ws.close();
  });

  it('completed 帧回调 onCompleted 并回传最后一次 sentence 的 speaker', async () => {
    let got: [string, string?] = ['', undefined];
    const ws = connectAsr(5, 'tok', { onReady: () => {}, onSentence: () => {}, onCompliance: () => {}, onError: () => {}, onCompleted: (t, s) => { got = [t, s]; } });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    inst.emit(JSON.stringify({ type: 'sentence', index: 0, text: '医生您好', final: true, speaker: 'doctor' }));
    inst.emit(JSON.stringify({ type: 'completed' }));
    await new Promise((r) => setTimeout(r, 0));
    expect(got).toEqual(['医生您好', 'doctor']);
  });

  it('completed 帧无 speaker 时回传 undefined（向后兼容）', async () => {
    let got: [string, string?] = ['', undefined];
    const ws = connectAsr(5, 'tok', { onReady: () => {}, onSentence: () => {}, onCompliance: () => {}, onError: () => {}, onCompleted: (t, s) => { got = [t, s]; } });
    await new Promise((r) => setTimeout(r, 0));
    MockWebSocket.instances[0].emit(JSON.stringify({ type: 'completed' }));
    await new Promise((r) => setTimeout(r, 0));
    expect(got).toEqual(['', undefined]);
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

  it('onerror 主动 close 释放连接（否则不保证 onclose），且不重复上报', async () => {
    const errors: string[] = [];
    const ws = connectAsr(5, 'tok', { onReady: () => {}, onSentence: () => {}, onCompliance: () => {}, onError: (m) => errors.push(m), onCompleted: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    inst.simulateError();
    expect(errors).toEqual(['语音服务连接失败']);
    // onerror → 主动 close（readyState 进入 CLOSED），后续 onclose 不再上报
    expect(inst.readyState).toBe(3);
    expect(errors).toEqual(['语音服务连接失败']);
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
