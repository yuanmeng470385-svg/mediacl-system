import { connectAsrStreaming } from '../asr';

// recorder.ts 模块级 import react-native-audio-record：包体是 ESM 且 jest 不转译 node_modules
// （transformIgnorePatterns 不含它），且 jest 下 Platform.OS=ios 时 NativeEventEmitter(null) 抛错
// → 必须 mock，否则测试文件模块加载失败
jest.mock('react-native-audio-record', () => ({
  default: { init: jest.fn(), start: jest.fn(), stop: jest.fn(), on: jest.fn() },
}));

// readPcmSource 用 RNFS.read(path, length, position, encoding) 做增量读（readFile 不支持 position/length）；
// DocumentDirectoryPath 供 Android temp.pcm 源判定（recorder.ts 的 TEMP_PCM_PATH 组合用）
jest.mock('react-native-fs', () => ({
  DocumentDirectoryPath: '/data/user/0/com.medagent/files',
  read: jest.fn(),
  stat: jest.fn(),
}));
import RNFS from 'react-native-fs';
import { Platform } from 'react-native';

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
 * flush 串行链使每轮 flushTo 再延 1-2 跳（flushTail.then 包裹）→ 初始轮约 9 跳；
 * 多跑几跳保证时序稳定（不改变断言含义）。
 */
async function settle(turns = 12) {
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
    // sent[0] 是 auth 帧（B5 首帧鉴权），音频分片从 sent[1] 起
    expect(ws.sent[0]).toBe(JSON.stringify({ type: 'auth', token: 't' }));
    const chunk = new Uint8Array(ws.sent[1]);
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
    // 帧顺序：auth 帧（B5 首帧鉴权）→ 初始 PCM → 剩余 PCM → stop
    const frames = ws.sent;
    expect(frames.length).toBe(4); // auth + 初始分片 + 剩余分片 + stop 帧
    expect(frames[0]).toBe(JSON.stringify({ type: 'auth', token: 't' }));
    expect(Array.from(new Uint8Array(frames[2]))).toEqual(Array.from(new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20])));
    expect(frames[3]).toBe(JSON.stringify({ type: 'stop' }));
  });

  test('stop 早于 WS open：不发送任何帧，open 后补 flush + stop 帧（防按钮卡死与服务端孤儿）', async () => {
    // CONNECTING 起步的 WS 变体：readyState 从 0 开始，手动 open() 触发 onopen 才置 OPEN
    class ConnectingWebSocket extends MockWebSocket {
      readyState = MockWebSocket.CONNECTING;
      open() {
        this.readyState = MockWebSocket.OPEN;
        this.onopen && this.onopen();
      }
    }
    (global as any).WebSocket = ConnectingWebSocket;
    const cbs = { onReady: jest.fn(), onSentence: jest.fn(), onCompliance: jest.fn(), onError: jest.fn(), onCompleted: jest.fn() };
    const session = connectAsrStreaming(1, 't', '/tmp/rec.wav', cbs);
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1] as ConnectingWebSocket;
    // 建连前 stop：pre-open 的任何发送（分片/stop 帧）都会被 connectAsr 的 OPEN 门禁丢弃，
    // offset 也不能被白白推进 → 挂起，此时必须零发送
    session.stop();
    expect(ws.sent.length).toBe(0);
    // WS 打开 → onReady → 挂起的收尾执行：auth 帧（B5 首帧鉴权）→ flush 全部已录
    // PCM（offset 从头算）→ stop 帧
    ws.open();
    await settle();
    const frames = ws.sent;
    expect(frames.length).toBe(3); // auth + flush 分片 + stop 帧
    expect(frames[0]).toBe(JSON.stringify({ type: 'auth', token: 't' }));
    expect(Array.from(new Uint8Array(frames[1]))).toEqual(Array.from(pcmBuffer));
    expect(frames[2]).toBe(JSON.stringify({ type: 'stop' }));
  });

  test('Android：录音中增量读源为 temp.pcm（裸 PCM 无头），temp 删除后切回 wav(+44)', async () => {
    // jest 预设（Platform.ios.js）下 Platform.OS 是平铺属性 'ios'，临时切 android，用毕还原
    const origOS = Platform.OS;
    Platform.OS = 'android';
    // 上一条用例（pre-open stop）把全局 WebSocket 换成了 CONNECTING 起步的变体，这里恢复
    (global as any).WebSocket = MockWebSocket;
    try {
      const wavPath = `${RNFS.DocumentDirectoryPath}/medagent_rec.wav`;
      const tempPath = `${RNFS.DocumentDirectoryPath}/temp.pcm`;
      // 录音中：temp.pcm 存在（10 字节裸 PCM），wav 尚未生成
      (RNFS.stat as jest.Mock).mockImplementation(async (p: string) => {
        if (p === tempPath) return { size: 10 };
        throw new Error('ENOENT: wav not yet materialized');
      });
      // temp 分支读的是裸文件字节偏移（无 44 头）
      (RNFS.read as jest.Mock).mockImplementation(async (p: string, len: number, pos: number) => {
        const slice = pcmBuffer.subarray(pos, pos + len);
        return toBase64(slice);
      });
      const cbs = { onReady: jest.fn(), onSentence: jest.fn(), onCompliance: jest.fn(), onError: jest.fn(), onCompleted: jest.fn() };
      connectAsrStreaming(1, 't', wavPath, cbs);
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
      ws.onopen && ws.onopen();
      // Android 路径每次源判定多 1 次 stat（tempPcmExists + stat），start 链约 12 跳（iOS 约 7 跳）
      await settle(24);
      // 录音中：temp.pcm 的 10 字节整段推走（证明读的是裸 PCM，不是不存在的 wav）
      const firstChunks = ws.sent.filter((s) => s instanceof ArrayBuffer);
      expect(firstChunks.length).toBe(1);
      expect(Array.from(new Uint8Array(firstChunks[0]))).toEqual(Array.from(pcmBuffer));
      // 裸 PCM 契约：文件偏移 = PCM 偏移（无 44 头）
      expect((RNFS.read as jest.Mock).mock.calls[0]).toEqual([tempPath, 10, 0, 'base64']);
      // stop 完成：temp.pcm 已删，wav 落盘（44 头 + 20 PCM）→ 下一轮轮询切回 wav 契约（文件偏移 = PCM 偏移 + 44）
      (RNFS.stat as jest.Mock).mockImplementation(async (p: string) => {
        if (p === tempPath) throw new Error('ENOENT: temp deleted after stop');
        return { size: 44 + 20 };
      });
      (RNFS.read as jest.Mock).mockImplementation(async (p: string, len: number, pos: number) => {
        const start = pos - 44; // wav 契约：文件偏移 = PCM 偏移 + 44
        const extra = new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
        const slice = start >= 10 ? extra.subarray(start - 10, start - 10 + (len === 0 ? extra.length : len)) : new Uint8Array(0);
        return toBase64(slice);
      });
      flushTimers();
      await settle(24);
      // 切源后 offset 连续（temp 的 10 字节已推过）：只推 wav 新增的 11-20，且读位置带 44 头偏移
      const chunks = ws.sent.filter((s) => s instanceof ArrayBuffer);
      expect(chunks.length).toBe(2);
      expect(Array.from(new Uint8Array(chunks[1]))).toEqual(Array.from(new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20])));
      expect((RNFS.read as jest.Mock).mock.calls[1]).toEqual([wavPath, 10, 54, 'base64']);
    } finally {
      Platform.OS = origOS;
    }
  });

  test('轮询重入门禁：上一轮未完成时跳过本轮，不叠推', async () => {
    const { ws, session } = openSession();
    await settle(); // 初始轮：10 字节推完
    // 录音增长 + 慢读：round 1 读到新增量时挂起（offset=10, until=20 → 必须真读才卡得住）
    (RNFS.stat as jest.Mock).mockResolvedValue({ size: 44 + 20 });
    let resolveRead: (v: string) => void = () => {};
    (RNFS.read as jest.Mock).mockReturnValueOnce(
      new Promise<string>((r) => { resolveRead = r; }),
    );
    flushTimers(); // round 1：pushing=true → stat(20) → read 挂起
    await settle();
    const readsAfterRound1 = (RNFS.read as jest.Mock).mock.calls.length; // 2（初始 + round1）
    flushTimers(); // round 2：应被重入门禁挡下，不再 stat/read
    await settle();
    expect((RNFS.read as jest.Mock).mock.calls.length).toBe(readsAfterRound1); // round 2 未新增 read
    expect((RNFS.stat as jest.Mock).mock.calls.length).toBe(2); // round 2 未新增 stat
    resolveRead(toBase64(new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20]))); // 放行 round 1
    await settle();
    session.stop();
    await settle();
    const chunks = ws.sent.filter((s) => s instanceof ArrayBuffer);
    expect(chunks.length).toBe(2); // 初始 + round1 增量，round 2 未叠推
    expect(ws.sent[ws.sent.length - 1]).toBe(JSON.stringify({ type: 'stop' }));
  });

  test('空块自旋守卫：read 返回 0 字节时本轮终止，不无限重试', async () => {
    const { ws, session } = openSession();
    (RNFS.read as jest.Mock).mockResolvedValue(''); // 恒空读（0 字节）
    // 多跑几跳（每轮重试约 2 跳）：无守卫时 pushSince 会在同一 0 字节窗口内无限重试 read；
    // 有守卫时本轮只读一次，settle 内 read 调用不随跳数增长
    await settle(40);
    session.stop(); // stop 后 finalize 同样应能收尾（0 字节 flush 直接跳过 → 发 stop 帧）
    await settle();
    const frames = ws.sent;
    expect(frames[frames.length - 1]).toBe(JSON.stringify({ type: 'stop' }));
    // 判别点：read 调用次数有界（初始轮 1 次 + finalize 1 次）
    expect((RNFS.read as jest.Mock).mock.calls.length).toBeLessThanOrEqual(2);
  });

  test('flush 串行化：stop 与初始推流并发时不双发同分片', async () => {
    // 让初始轮的 flush 已入读（read 在途）→ 期间 stop() → finalize 的 flush 与初始 flush 并发：
    // 无串行链时两个 flushTo 同时从 offset=0 读 → 双发同分片；串行化后后者排在链尾、offset 已推进 → 不重发
    let resolveRead: (v: string) => void = () => {};
    const pendingRead = new Promise<string>((r) => { resolveRead = r; });
    const cbs = { onReady: jest.fn(), onSentence: jest.fn(), onCompliance: jest.fn(), onError: jest.fn(), onCompleted: jest.fn() };
    const session = connectAsrStreaming(1, 't', '/tmp/rec.wav', cbs);
    (RNFS.read as jest.Mock).mockReturnValueOnce(pendingRead); // 首读（初始轮）挂起
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    ws.onopen && ws.onopen(); // onReady → start → 初始轮：stat(44+10) → flushTo 的 read 挂起
    await settle(4); // 初始 flush 的 read 在途
    session.stop(); // stop 落在初始 flush 在途期间：finalizeStop 立即 stat（取 44+10）并并发 flush
    expect((RNFS.stat as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(2);
    resolveRead(toBase64(pcmBuffer)); // 放行初始轮 read
    await settle();
    const frames = ws.sent.filter((s) => s instanceof ArrayBuffer);
    // 串行化后：10 字节恰好发一次（无双发、无 offset 双重推进 → 无空窗）
    expect(frames.length).toBe(1);
    expect(Array.from(new Uint8Array(frames[0]))).toEqual(Array.from(pcmBuffer));
    expect(ws.sent[ws.sent.length - 1]).toBe(JSON.stringify({ type: 'stop' }));
  });
});
