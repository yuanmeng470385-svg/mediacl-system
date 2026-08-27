/** 医生端 WS 流式客户端测试（照 rep 端 mobile wsChat.test.ts 范式） */
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
  readyState = 0;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  send(data: any) { this.sent.push(data); }
  close() { this.readyState = 3; }
  triggerOpen() {
    this.readyState = 1;
    this.onopen?.();
  }
  simulateClose() {
    this.onclose?.({});
  }
  simulateError() {
    this.onerror?.({});
  }
  emit(data: any) { this.onmessage?.({ data }); }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  (global as any).WebSocket = MockWebSocket;
});

const noopCbs = { onStart: () => {}, onDelta: () => {}, onDone: () => {}, onError: () => {} };

describe('医生端 wsChat 客户端', () => {
  it('URL 走网关且不含 token（B5：token 移出 query，改首帧 auth）', () => {
    const ws = openChatWs(3, 'tok-1', noopCbs);
    const inst = MockWebSocket.instances[0];
    expect(inst.url).toContain(':8000/api/v1/specialists/3/chat/ws');
    expect(inst.url).not.toContain('token=');
    ws.close();
  });

  it('onopen 首帧发 auth 帧，再发 question 帧', () => {
    const ws = openChatWs(3, 'tok', noopCbs);
    const inst = MockWebSocket.instances[0];
    inst.triggerOpen();
    ws.sendQuestion('你好', 'sess-1');
    expect(inst.sent[0]).toBe(JSON.stringify({ type: 'auth', token: 'tok' }));
    expect(inst.sent[1]).toBe(JSON.stringify({ type: 'question', text: '你好', session_id: 'sess-1' }));
    ws.close();
  });

  it('open 前 sendQuestion 缓冲，open 后 auth 帧 + question 帧顺序补发', () => {
    const ws = openChatWs(3, 'tok', noopCbs);
    const inst = MockWebSocket.instances[0];
    ws.sendQuestion('你好');
    expect(inst.sent).toHaveLength(0);
    inst.triggerOpen();
    expect(inst.sent[0]).toBe(JSON.stringify({ type: 'auth', token: 'tok' }));
    expect(inst.sent[1]).toBe(JSON.stringify({ type: 'question', text: '你好' }));
    ws.close();
  });

  it('start → delta → done 逐帧回调；done 聚合 blocked/violations/citations', () => {
    const cbs = {
      onStart: jest.fn(), onDelta: jest.fn(), onDone: jest.fn(), onError: jest.fn(),
    };
    const ws = openChatWs(3, 'tok', cbs);
    const inst = MockWebSocket.instances[0];
    inst.triggerOpen();
    ws.sendQuestion('问题');
    inst.emit(JSON.stringify({ type: 'start' }));
    inst.emit(JSON.stringify({ type: 'delta', text: '你' }));
    inst.emit(JSON.stringify({ type: 'delta', text: '好' }));
    inst.emit(JSON.stringify({
      type: 'done', text: '好的',
      session_id: 's1', conversation_id: 7,
      citations: [{ title: '文献' }], blocked: true,
      violations: [{ rule_code: 'R001', matched_text: '违规词' }],
    }));
    expect(cbs.onStart).toHaveBeenCalledTimes(1);
    expect(cbs.onDelta.mock.calls.map((c) => c[0])).toEqual(['你', '好']);
    expect(cbs.onDone).toHaveBeenCalledWith({
      text: '好的', conversationId: 7, sessionId: 's1',
      citations: [{ title: '文献' }], blocked: true,
      violations: [{ rule_code: 'R001', matched_text: '违规词' }],
    });
    expect(cbs.onError).not.toHaveBeenCalled();
    ws.close();
  });

  it('error 帧回调 onError；主动 close 后 onclose 不上报故障', () => {
    const cbs = { onStart: jest.fn(), onDelta: jest.fn(), onDone: jest.fn(), onError: jest.fn() };
    const ws = openChatWs(3, 'tok', cbs);
    const inst = MockWebSocket.instances[0];
    inst.triggerOpen();
    inst.emit(JSON.stringify({ type: 'error', message: '服务异常' }));
    expect(cbs.onError).toHaveBeenCalledWith('服务异常');
    ws.close();
    inst.simulateClose();
    expect(cbs.onError).toHaveBeenCalledTimes(1);
  });

  it('中途断开（未主动 close）onclose 上报故障', () => {
    const cbs = { onStart: jest.fn(), onDelta: jest.fn(), onDone: jest.fn(), onError: jest.fn() };
    const ws = openChatWs(3, 'tok', cbs);
    const inst = MockWebSocket.instances[0];
    inst.triggerOpen();
    inst.simulateClose();
    expect(cbs.onError).toHaveBeenCalledWith('对话连接已断开');
    ws.close();
  });

  it('onerror 回调后主动 close（RN 实现差异：onerror 后不保证 onclose）', () => {
    const cbs = { onStart: jest.fn(), onDelta: jest.fn(), onDone: jest.fn(), onError: jest.fn() };
    const ws = openChatWs(3, 'tok', cbs);
    const inst = MockWebSocket.instances[0];
    inst.triggerOpen();
    inst.simulateError();
    expect(cbs.onError).toHaveBeenCalledWith('对话服务连接失败');
    expect(inst.readyState).toBe(3);               // 主动 close 释放连接
    ws.close();
  });
});
