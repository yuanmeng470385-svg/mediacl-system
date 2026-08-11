import { connectAsrStreaming } from '../asr';

// recorder.ts 模块级 import react-native-audio-record：包体是 ESM 且 jest 不转译 node_modules
// （transformIgnorePatterns 不含它），且 jest 下 Platform.OS=ios 时 NativeEventEmitter(null) 抛错
// → 必须 mock，否则测试文件模块加载失败
jest.mock('react-native-audio-record', () => ({
  default: { init: jest.fn(), start: jest.fn(), stop: jest.fn(), on: jest.fn() },
}));

// readWavPcmFrom 用 RNFS.read(path, length, position, encoding) 做增量读（readFile 不支持 position/length）
jest.mock('react-native-fs', () => ({
  read: jest.fn(),
  stat: jest.fn(),
}));
import RNFS from 'react-native-fs';

const pcmBuffer = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);

function toBase64(bytes: Uint8Array): string {
  let bin = '';
  bytes.forEach((b) => { bin += String.fromCharCode(b); });
  return Buffer.from(bin, 'binary').toString('base64');
}

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CONNECTING = 0;
  readyState = MockWebSocket.OPEN;
  url: string;
  onopen: any = null;
  onmessage: any = null;
  onerror: any = null;
  onclose: any = null;
  sent: any[] = [];
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  send(data: any) { this.sent.push(data); }
  close() { this.readyState = 3; }
}

(global as any).WebSocket = MockWebSocket;

/** 让轮询用假时钟推进 */
function flushTimers() {
  jest.runOnlyPendingTimers();
}

/**
 * 让 mock 异步链跑完：每次 mock 调用（stat/read）的 await 占一跳，
 * start/轮询链约 3-4 跳、stop 收尾链（stat → then → read → send → 完成 → catch → finally）约 7 跳；
 * 多跑几跳保证时序稳定（不改变断言含义）。
 */
async function settle(turns = 8) {
  for (let i = 0; i < turns; i++) await Promise.resolve();
}

describe('connectAsrStreaming', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    MockWebSocket.instances = [];
    (RNFS.stat as jest.Mock).mockResolvedValue({ size: 44 + 10 }); // 10 字节 PCM
    // RNFS.read(path, length, position)：position 为文件字节偏移，返回该窗口的 base64
    (RNFS.read as jest.Mock).mockImplementation(async (_p: string, len: number, pos: number) => {
      const start = pos - 44;
      const end = Math.min(pcmBuffer.length, start + (len === 0 ? pcmBuffer.length : len));
      const slice = pcmBuffer.subarray(Math.max(0, start), end);
      return toBase64(slice);
    });
  });
  afterEach(() => {
    jest.useRealTimers();
    jest.clearAllMocks();
  });

  function openSession() {
    const cbs = { onReady: jest.fn(), onSentence: jest.fn(), onCompliance: jest.fn(), onError: jest.fn(), onCompleted: jest.fn() };
    const session = connectAsrStreaming(1, 't', '/tmp/rec.wav', cbs);
    // connectAsr 内部 new WebSocket(url)（全局 mock 接管）→ 取它创建的实例，
    // 手动触发 onopen 模拟 WS 建连 → onReady
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    ws.onopen && ws.onopen();
    return { ws, cbs, session };
  }

  test('onReady 后把已录 PCM 分片推完', async () => {
    const { ws } = openSession();
    await settle();
    expect(ws.sent.filter((s) => s instanceof ArrayBuffer).length).toBe(1);
    const chunk = new Uint8Array(ws.sent[0]);
    expect(Array.from(chunk)).toEqual(Array.from(pcmBuffer));
  });

  test('轮询期间追加的录音被增量推送', async () => {
    const { ws } = openSession();
    await settle();
    // 录音增长：10 → 20 字节
    (RNFS.stat as jest.Mock).mockResolvedValue({ size: 44 + 20 });
    (RNFS.read as jest.Mock).mockImplementation(async (_p: string, len: number, pos: number) => {
      const start = pos - 44;
      const extra = new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
      const slice = start >= 10 ? extra.subarray(start - 10, start - 10 + (len === 0 ? extra.length : len)) : new Uint8Array(0);
      return toBase64(slice);
    });
    flushTimers();
    await settle();
    const chunks = ws.sent.filter((s) => s instanceof ArrayBuffer);
    expect(chunks.length).toBe(2); // 初始 + 增量
    expect(Array.from(new Uint8Array(chunks[1]))).toEqual(Array.from(new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20])));
  });

  test('stop 推完剩余并发 stop 帧', async () => {
    const { ws, session } = openSession();
    await settle();
    // 录音增长：10 → 20 字节（最后 pollMs 内录下的尾音尚未被轮询推走）
    (RNFS.stat as jest.Mock).mockResolvedValue({ size: 44 + 20 });
    (RNFS.read as jest.Mock).mockImplementation(async (_p: string, len: number, pos: number) => {
      const start = pos - 44;
      const extra = new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
      const slice = start >= 10 ? extra.subarray(start - 10, start - 10 + (len === 0 ? extra.length : len)) : new Uint8Array(0);
      return toBase64(slice);
    });
    session.stop();
    await settle();
    // 帧顺序：剩余 PCM 二进制分片在前，stop 帧在后
    const frames = ws.sent;
    expect(frames.length).toBe(3); // 初始分片 + 剩余分片 + stop 帧
    expect(Array.from(new Uint8Array(frames[1]))).toEqual(Array.from(new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20])));
    expect(frames[2]).toBe(JSON.stringify({ type: 'stop' }));
  });
});
