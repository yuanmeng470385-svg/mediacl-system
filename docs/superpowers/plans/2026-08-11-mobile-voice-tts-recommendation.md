# mobile 语音链路补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移动端语音链路补全：host 集中可配置、录音流式推流（M19 修复）、NLS TTS 朗读话术、拜访中 AI 实时推荐区（关键节点 + 话术建议）、ChatScreen 文案更新。

**Architecture:** 新增 `src/config.ts` 集中三个 host（API/ASR/聊天 WS）；recorder.ts 用 RNFS.readFile 的 position/length 支持增量读 PCM，asr.ts 新增 `connectAsrStreaming`（轮询增量推流，服务端 asr_ws.py 零改动）；新增 `src/services/tts.ts`（服务端 tts-token → NLS REST 合成 → react-native-sound 播放）；visit.ts 的 `mapTranscriptResult` 扩展解析 `key_nodes`/`ai_suggestion`，VisitInProgressScreen 渲染推荐区。

**Tech Stack:** React Native 0.75 + TypeScript + jest（`cd mobile && npx jest`）。已依赖：react-native-fs（RNFS，支持 position/length）、react-native-audio-record。新增依赖：react-native-sound（已获用户批准，Task 3 安装）。

## Global Constraints

- 测试命令：`cd mobile && npx jest`（或 `npx jest <file>` 单文件）；全量基线 50 用例
- 映射铁律：后端响应形状统一在 `src/api/*.ts` 映射，屏幕组件只消费映射结果
- config.ts 是唯一允许写死 host 的地方；client.ts/asr.ts/wsChat.ts 必须改为读 config
- 服务端 asr_ws.py / visit-service 本轮零改动（Plan 2026-08-11-visit-tts-and-llm-recommendation 提供 tts-token 端点）
- 每个任务结束跑 jest + 提交一个 commit

---

### Task 1: config.ts 集中 host 配置

**Files:**
- Create: `mobile/src/config.ts`
- Modify: `mobile/src/api/client.ts`（L6-14）
- Modify: `mobile/src/services/asr.ts`（L8-14）
- Modify: `mobile/src/services/wsChat.ts`（L5-11）

**Interfaces:**
- Produces: `API_HOST` / `ASR_HOST` / `GATEWAY_HOST`（均为不含协议、不含端口的 host 名）；下游 tts.ts 复用 `API_HOST` 语义（走 client.ts）
- Consumes: 无

- [ ] **Step 1: 新建 `src/config.ts`**

```ts
import { Platform } from 'react-native';

/**
 * 集中管理后端地址（真机联调只改这里）：
 *   - 模拟器：Android 用 10.0.2.2（宿主机回环），iOS 用 localhost
 *   - 真机：改为电脑局域网 IP（如 '192.168.1.100'），并确保后端服务监听 0.0.0.0
 * 三个入口：API（REST，网关 8000）/ ASR（WS，visit-service 8002 直连）/ 聊天 WS（网关 8000）
 */
const DEV_HOST = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
// 真机联调：取消下行注释并改为电脑局域网 IP，模拟器验证时保留上行
// const DEV_HOST = '192.168.1.100';

export const API_HOST = DEV_HOST;
export const ASR_HOST = DEV_HOST;
export const GATEWAY_HOST = DEV_HOST;
```

- [ ] **Step 2: client.ts 改读 config**

`mobile/src/api/client.ts`：删 `import { Platform } from 'react-native';`（L7，仅 baseURL 用到），改为：

```ts
import { API_HOST } from '../config';

// 开发环境用本地网关，生产环境用正式地址；host 集中定义在 src/config.ts（真机联调改一处）
const API_BASE_URL = `http://${API_HOST}:8000`;
```

（其余不动）

- [ ] **Step 3: asr.ts / wsChat.ts 改读 config**

`mobile/src/services/asr.ts`：删 L8-14 的 `Platform.select` 块与 `import { Platform } from 'react-native';`，改为：

```ts
import { ASR_HOST } from '../config';
```

`mobile/src/services/wsChat.ts`：删 L5-11 的 `Platform.select` 块与 `import { Platform } from 'react-native';`，改为：

```ts
import { GATEWAY_HOST } from '../config';
```

- [ ] **Step 4: 跑 jest 确认无回归**

Run: `cd mobile && npx jest`
Expected: 50 passed（config 导入不影响既有用例；若 react-native preset 下 `Platform.OS` 为 'ios'，仅影响常量取值，不影响断言）

- [ ] **Step 5: 提交**

```bash
git add mobile/src/config.ts mobile/src/api/client.ts mobile/src/services/asr.ts mobile/src/services/wsChat.ts
git commit -m "refactor(mobile): host 集中到 config.ts（真机联调单点修改）"
```

---

### Task 2: 录音增量读 + ASR 流式推流（M19 修复）

**Files:**
- Modify: `mobile/src/services/recorder.ts`（追加两个函数）
- Modify: `mobile/src/services/asr.ts`（追加 `connectAsrStreaming`）
- Create: `mobile/src/services/__tests__/asrStreaming.test.ts`

**Interfaces:**
- Consumes: `connectAsr(visitId, token, cbs): AsrSession`（asr.ts 现有，协议不变）、`AsrCallbacks`（现有）
- Produces: `readWavPcmFrom(path, offset, length=0): Promise<Uint8Array>`、`wavDataLength(path): Promise<number>`、`connectAsrStreaming(visitId, token, wavPath, cbs, opts?): AsrSession`；下游 Task 4 的 VisitInProgressScreen 改用流式

- [ ] **Step 1: recorder.ts 追加增量读函数**

`mobile/src/services/recorder.ts` 的 `readWavPcm`（L32-39）之后追加：

```ts
/**
 * 读 wav 文件从 offset（PCM 字节偏移，跳过 44 字节头）起的 PCM 数据；
 * length=0 表示读到文件末尾。录音进行中轮询增量读取用（边录边推）。
 */
export async function readWavPcmFrom(path: string, offset: number, length = 0): Promise<Uint8Array> {
  const base64 = await RNFS.readFile(path, 'base64', offset + 44, length);
  const binary = atob(base64);
  const raw = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) raw[i] = binary.charCodeAt(i);
  return raw;
}

/** wav 文件 PCM 数据总长度（文件字节 - 44 字节头） */
export async function wavDataLength(path: string): Promise<number> {
  const st = await RNFS.stat(path);
  return Math.max(0, st.size - 44);
}
```

（RNFS.readFile 的 position/length 为字节级偏移，length=0 读至 EOF）

- [ ] **Step 2: asr.ts 追加流式会话**

`mobile/src/services/asr.ts` 文件末尾追加（先 `import { readWavPcmFrom, wavDataLength } from './recorder';` 加在文件头 import 区）：

```ts
export interface AsrStreamingOptions {
  /** 轮询读录音增量间隔 ms */
  pollMs?: number;
  /** 单次推流分片字节数 */
  chunkSize?: number;
}

/**
 * 流式转写（M19 修复）：录音进行中每 pollMs 轮询读 WAV 增量 → 持续推流，
 * 替代旧的"录完一次性推全部 + 立即 stop"（与 NLS 流式识别不匹配）。
 * 服务端 asr_ws.py 已支持持续二进制 feed + stop 收尾，零改动。
 * 使用方式：录音 start 后调用，stop 录音后调用返回会话的 stop()。
 */
export function connectAsrStreaming(
  visitId: number,
  token: string,
  wavPath: string,
  cbs: AsrCallbacks,
  opts: AsrStreamingOptions = {},
): AsrSession {
  const pollMs = opts.pollMs ?? 2000;
  const chunkSize = opts.chunkSize ?? 16 * 1024;
  let offset = 0; // 已推送的 PCM 字节偏移
  let timer: ReturnType<typeof setInterval> | null = null;
  let stopped = false;

  const session = connectAsr(visitId, token, {
    ...cbs,
    onReady: () => {
      start();
    },
  });

  async function pushSince(until: number) {
    while (offset < until && !stopped) {
      const chunk = await readWavPcmFrom(wavPath, offset, Math.min(chunkSize, until - offset));
      if (chunk.length === 0) break;
      session.sendAudioChunk(chunk);
      offset += chunk.length;
    }
  }

  async function start() {
    try {
      const total = await wavDataLength(wavPath);
      await pushSince(total);
    } catch {
      // 初始读失败忽略，下一轮重试
    }
    if (stopped) return;
    timer = setInterval(async () => {
      try {
        const total = await wavDataLength(wavPath);
        await pushSince(total);
      } catch {
        // 读失败忽略，下一轮重试
      }
    }, pollMs);
  }

  return {
    sendAudioChunk: session.sendAudioChunk.bind(session),
    stop() {
      if (stopped) return;
      stopped = true;
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      // 推完剩余 PCM 再发 stop 收尾
      wavDataLength(wavPath)
        .then((total) => pushSince(total))
        .catch(() => {})
        .finally(() => session.stop());
    },
    close() {
      stopped = true;
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      session.close();
    },
  };
}
```

- [ ] **Step 3: 写测试 `src/services/__tests__/asrStreaming.test.ts`**

（风格参照现有 `src/services/__tests__/asr.test.ts`；react-native preset 下需 mock RNFS 与 WebSocket）

```ts
import { connectAsrStreaming } from '../asr';

jest.mock('react-native-fs', () => ({
  readFile: jest.fn(),
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
  static OPEN = 1;
  static CONNECTING = 0;
  readyState = MockWebSocket.OPEN;
  onopen: any = null;
  onmessage: any = null;
  onerror: any = null;
  onclose: any = null;
  sent: any[] = [];
  constructor(public url: string) {}
  send(data: any) { this.sent.push(data); }
  close() { this.readyState = 3; }
}

(global as any).WebSocket = MockWebSocket;

/** 让轮询用假时钟推进 */
function flushTimers() {
  jest.runOnlyPendingTimers();
}

describe('connectAsrStreaming', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    (RNFS.stat as jest.Mock).mockResolvedValue({ size: 44 + 10 }); // 10 字节 PCM
    (RNFS.readFile as jest.Mock).mockImplementation(async (_p: string, _e: string, pos: number, len: number) => {
      // readFile 返回 pos 起 len 字节的 base64
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
    const ws = new MockWebSocket('ws://x/ws/visits/1/asr?token=t');
    const cbs = { onReady: jest.fn(), onSentence: jest.fn(), onCompliance: jest.fn(), onError: jest.fn(), onCompleted: jest.fn() };
    const session = connectAsrStreaming(1, 't', '/tmp/rec.wav', cbs);
    // 模拟 WS open → 触发 onReady
    ws.onopen && ws.onopen();
    return { ws, cbs, session };
  }

  test('onReady 后把已录 PCM 分片推完', async () => {
    const { ws } = openSession();
    await Promise.resolve(); // 让 start() 的异步读完
    expect(ws.sent.filter((s) => s instanceof ArrayBuffer).length).toBe(1);
    const chunk = new Uint8Array(ws.sent[0]);
    expect(Array.from(chunk)).toEqual(Array.from(pcmBuffer));
  });

  test('轮询期间追加的录音被增量推送', async () => {
    const { ws } = openSession();
    await Promise.resolve();
    // 录音增长：10 → 20 字节
    (RNFS.stat as jest.Mock).mockResolvedValue({ size: 44 + 20 });
    (RNFS.readFile as jest.Mock).mockImplementation(async (_p: string, _e: string, pos: number, len: number) => {
      const start = pos - 44;
      const extra = new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20]);
      const slice = start >= 10 ? extra.subarray(start - 10, start - 10 + (len === 0 ? extra.length : len)) : new Uint8Array(0);
      return toBase64(slice);
    });
    flushTimers();
    await Promise.resolve();
    const chunks = ws.sent.filter((s) => s instanceof ArrayBuffer);
    expect(chunks.length).toBe(2); // 初始 + 增量
    expect(Array.from(new Uint8Array(chunks[1]))).toEqual(Array.from(new Uint8Array([11, 12, 13, 14, 15, 16, 17, 18, 19, 20])));
  });

  test('stop 推完剩余并发 stop 帧', async () => {
    const { ws, session } = openSession();
    await Promise.resolve();
    session.stop();
    await Promise.resolve();
    const textFrames = ws.sent.filter((s) => typeof s === 'string');
    expect(textFrames).toEqual([JSON.stringify({ type: 'stop' })]);
  });
});
```

注意：`start()` 里 `setInterval` 回调是 async，jest fake timers 下 `runOnlyPendingTimers` 会执行；若断言时序不稳，把 `await Promise.resolve()` 在 flushTimers 后重复调用（最多两次）。

- [ ] **Step 4: 跑测试**

Run: `cd mobile && npx jest src/services/__tests__/asrStreaming.test.ts`
Expected: 3 passed（若有断言时序问题按 Step 3 尾注调整）

- [ ] **Step 5: 全量 jest**

Run: `cd mobile && npx jest`
Expected: 53 passed

- [ ] **Step 6: 提交**

```bash
git add mobile/src/services/recorder.ts mobile/src/services/asr.ts mobile/src/services/__tests__/asrStreaming.test.ts
git commit -m "feat(mobile): ASR 流式推流（M19 修复，轮询增量读 WAV → 持续推送）"
```

---

### Task 3: NLS TTS 合成与朗读（react-native-sound）

**Files:**
- Create: `mobile/src/services/tts.ts`
- Create: `mobile/src/services/__tests__/tts.test.ts`
- Modify: `mobile/package.json`（新增 react-native-sound，npm install 自动）

**Interfaces:**
- Consumes: `apiClient.request<T>(method, path, data?)`（`src/api/client.ts` 命名导出，返回已解包的业务 data，code!==0 抛 APIError；路径带 `/api/v1` 前缀，与 `src/api/visit.ts` 等一致）、后端 `GET /api/v1/nls/tts-token`（Plan visit 产出，返回 `{token, appkey, expires_at}`）
- Produces: `getTtsToken(): Promise<{token, appkey}>`、`speak(text): Promise<void>`（合成并播放，播放中再调会打断重播）、`stopSpeaking(): void`；下游 Task 4 UI 朗读按钮

- [ ] **Step 1: 安装 react-native-sound**

Run: `cd mobile && npm install react-native-sound`
（原生模块：真机/模拟器需重新 `run-android` 才生效；jest 中用 mock 不需原生构建）

- [ ] **Step 2: 新建 `src/services/tts.ts`**

```ts
/**
 * NLS 语音合成（TTS）：服务端换发临时 token → NLS REST 一次性合成 → 本地播放。
 * 未配 NLS_APPKEY 时后端 tts-token 报业务错误（code 4xxx），speak 抛错由调用方提示。
 */
import RNFS from 'react-native-fs';
import Sound from 'react-native-sound';
import { apiClient } from '../api/client';

const TTS_URL = 'https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts';

let current: Sound | null = null;

export async function getTtsToken(): Promise<{ token: string; appkey: string }> {
  // apiClient.request 返回业务 data（{code,message,data} 已解包，与 src/api/*.ts 一致）
  const data = await apiClient.request<{ token?: string; appkey?: string }>('GET', '/api/v1/nls/tts-token');
  if (!data?.token || !data?.appkey) throw new Error('NLS 语音合成未配置');
  return { token: data.token, appkey: data.appkey };
}

/** 合成并播放话术文本；正在播放时打断重播 */
export async function speak(text: string): Promise<void> {
  const { token, appkey } = await getTtsToken();
  const url = `${TTS_URL}?appkey=${encodeURIComponent(appkey)}&token=${encodeURIComponent(token)}&text=${encodeURIComponent(text)}&format=wav&sample_rate=16000`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`语音合成失败(${resp.status})`);
  const bytes = new Uint8Array(await resp.arrayBuffer());
  let bin = '';
  bytes.forEach((b) => { bin += String.fromCharCode(b); });
  const b64 = btoa(bin);
  const path = `${RNFS.DocumentDirectoryPath}/tts_tmp.wav`;
  await RNFS.writeFile(path, b64, 'base64');

  await new Promise<void>((resolve, reject) => {
    stopSpeaking();
    const s = new Sound(path, '', (err) => {
      if (err) {
        reject(new Error('音频播放初始化失败'));
        return;
      }
      current = s;
      s.play(() => {
        s.release();
        if (current === s) current = null;
      });
      resolve();
    });
  });
}

export function stopSpeaking(): void {
  if (current) {
    current.stop();
    current.release();
    current = null;
  }
}
```

（`btoa` RN 运行时自带，与 recorder.ts 的 `atob` 同先例；`client.get` 沿用 `src/api/client.ts` 的调用形态——先确认 client.ts 的 get 方法签名与现有 api 文件用法一致，如 `services/user.ts` 中 `client.get(...)` 的用法）

- [ ] **Step 3: 写测试 `src/services/__tests__/tts.test.ts`**

```ts
import { getTtsToken, speak, stopSpeaking } from '../tts';

jest.mock('react-native-fs', () => ({
  readFile: jest.fn(),
  writeFile: jest.fn().mockResolvedValue(undefined),
  stat: jest.fn(),
  DocumentDirectoryPath: '/mock/doc',
}));
jest.mock('react-native-sound', () => {
  const mockPlay = jest.fn();
  const mockRelease = jest.fn();
  const mockStop = jest.fn();
  return jest.fn().mockImplementation((_path: string, _base: string, cb: (e: Error | null) => void) => {
    cb(null);
    return { play: mockPlay, release: mockRelease, stop: mockStop };
  });
});
jest.mock('../../api/client', () => ({
  __esModule: true,
  apiClient: { request: jest.fn() },
}));
import { apiClient } from '../../api/client';
import Sound from 'react-native-sound';

describe('tts', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  test('getTtsToken 请求 tts-token 并返回 token/appkey', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 'tok-1', appkey: 'app-1', expires_at: 0 });
    const r = await getTtsToken();
    expect(r).toEqual({ token: 'tok-1', appkey: 'app-1' });
    expect(apiClient.request).toHaveBeenCalledWith('GET', '/api/v1/nls/tts-token');
  });

  test('getTtsToken 缺 token 抛错', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({});
    await expect(getTtsToken()).rejects.toThrow('未配置');
  });

  test('speak 合成 URL 带 appkey/token/text 并写文件播放', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 'tok-1', appkey: 'app-1' });
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: async () => new Uint8Array([0x52, 0x49, 0x46, 0x46]).buffer,
    }) as any;
    const RNFS = require('react-native-fs');
    await speak('主任您好');
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('appkey=app-1'));
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('token=tok-1'));
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('text='));
    expect(RNFS.writeFile).toHaveBeenCalledWith('/mock/doc/tts_tmp.wav', expect.any(String), 'base64');
    expect(Sound).toHaveBeenCalled();
  });

  test('speak 合成失败抛错', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 }) as any;
    await expect(speak('x')).rejects.toThrow('500');
  });

  test('stopSpeaking 释放当前播放', () => {
    const s = new Sound('/x', '', () => {});
    (global as any).__ttsCurrent = s; // 内部 current 无法直接触碰，只验证不抛错
    expect(() => stopSpeaking()).not.toThrow();
  });
});
```

注意：若 `Sound` mock 的 `cb(null)` 同步触发导致 `current` 赋值后立刻被 `play` 回调清空，把 mock 改为 `cb` 延迟（`setTimeout(() => cb(null), 0)`）再补 `await`。测试目标是覆盖 getTtsToken 解包与 speak 的 URL/写文件路径，播放细节容错调整。

- [ ] **Step 4: 跑测试**

Run: `cd mobile && npx jest src/services/__tests__/tts.test.ts`
Expected: 5 passed（若 Sound mock 时序问题按 Step 3 尾注调整）

- [ ] **Step 5: 全量 jest**

Run: `cd mobile && npx jest`
Expected: 58 passed

- [ ] **Step 6: 提交**

```bash
git add mobile/src/services/tts.ts mobile/src/services/__tests__/tts.test.ts mobile/package.json mobile/package-lock.json
git commit -m "feat(mobile): NLS TTS 合成与朗读（tts.ts + react-native-sound）"
```

---

### Task 4: AI 实时推荐区 + 朗读按钮 + ChatScreen 文案

**Files:**
- Modify: `mobile/src/api/visit.ts`（TranscriptResult 类型 + `mapTranscriptResult`）
- Modify: `mobile/src/screens/VisitInProgress/VisitInProgressScreen.tsx`
- Modify: `mobile/src/screens/Chat/ChatScreen.tsx`（L215-222 handleVoice 文案）
- Modify: `mobile/src/api/__tests__/api-contract.test.ts`（mapTranscriptResult 新字段用例）

**Interfaces:**
- Consumes: Task 3 `speak(text)`；后端 transcript 响应新字段 `key_nodes` / `ai_suggestion`（Plan visit Task 3 产出）
- Produces: `KeyNode` / `AiSuggestion` 类型（visit.ts 导出）、TranscriptResult 新字段；屏幕消费

- [ ] **Step 1: visit.ts 扩展类型与映射**

`mobile/src/api/visit.ts` 中 `TranscriptResult` 类型定义处追加字段（并在其上方定义新类型）：

```ts
/** LLM 实时推荐：关键节点标记（服务端 visit_records.key_nodes 元素） */
export interface KeyNode {
  type: 'decision_point' | 'interest_point';
  label: string;
  quote: string;
}

/** LLM 实时推荐：话术建议 */
export interface AiSuggestion {
  topic: string;
  advice: string;
}
```

`TranscriptResult` 追加：

```ts
  key_nodes: KeyNode[];
  ai_suggestion: AiSuggestion | null;
```

`mapTranscriptResult` 的 return（现 L212-216）追加：

```ts
    key_nodes: Array.isArray(raw?.key_nodes)
      ? raw.key_nodes
          .filter((n: any): n is Record<string, unknown> => !!n && typeof n === 'object')
          .map((n: any) => ({
            type: n.type === 'interest_point' ? ('interest_point' as const) : ('decision_point' as const),
            label: String(n.label ?? '').slice(0, 20),
            quote: String(n.quote ?? '').slice(0, 60),
          }))
          .filter((n: KeyNode) => n.label)
      : [],
    ai_suggestion:
      raw?.ai_suggestion && typeof raw.ai_suggestion === 'object' && raw.ai_suggestion.advice
        ? {
            topic: String(raw.ai_suggestion.topic ?? '对话要点').slice(0, 50),
            advice: String(raw.ai_suggestion.advice).slice(0, 200),
          }
        : null,
```

- [ ] **Step 2: VisitInProgressScreen 加状态与接线**

`mobile/src/screens/VisitInProgress/VisitInProgressScreen.tsx`：

- 新 import：`import { speak } from '../../services/tts';`、`import type { KeyNode, AiSuggestion } from '../../api/visit';`（按现有 import 路径组织）
- 状态（现有 transcript/objections/complianceAlerts 附近）：

```tsx
  const [keyNodes, setKeyNodes] = useState<KeyNode[]>([]);
  const [aiSuggestion, setAiSuggestion] = useState<AiSuggestion | null>(null);
```

- `addTranscript`（L69-82）内 `sendTranscript` 成功后追加（现有 objections/compliance 处理之后）：

```tsx
      if (result.key_nodes?.length) setKeyNodes((prev) => [...prev, ...result.key_nodes]);
      if (result.ai_suggestion) setAiSuggestion(result.ai_suggestion);
```

- 朗读函数（addTranscript 附近）：

```tsx
  const speakTts = useCallback(async (text: string) => {
    try {
      await speak(text);
    } catch (e: any) {
      Alert.alert('语音合成', e?.message || '合成失败，请检查 NLS 配置');
    }
  }, []);
```

- 异议卡片（L236-245）内 `onPress` Alert 之外追加朗读小按钮（有建议话术时）：

```tsx
                  {obj.suggested_response && (
                    <TouchableOpacity
                      style={styles.speakBtn}
                      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                      onPress={() => speakTts(obj.suggested_response!)}>
                      <Icon name="volume-high" size={12} color={Colors.primary} />
                      <Text style={styles.speakText}>朗读</Text>
                    </TouchableOpacity>
                  )}
```

- 异议 section 之后新增「AI 实时推荐」section（complianceAlerts section 之前或之后，参照 sideSection 布局）：

```tsx
          {(keyNodes.length > 0 || aiSuggestion) && (
            <View style={styles.sideSection}>
              <View style={styles.sideTitleRow}>
                <Icon name="bulb-outline" size={14} color={Colors.primary} />
                <Text style={styles.sideTitle}>AI 实时推荐</Text>
              </View>
              {keyNodes.slice(-5).map((n, i) => (
                <View key={`kn_${i}`} style={styles.keyNodeRow}>
                  <Text style={[styles.keyNodeBadge, n.type === 'decision_point' ? styles.keyNodeDecision : styles.keyNodeInterest]}>
                    {n.type === 'decision_point' ? '决策点' : '兴趣点'}
                  </Text>
                  <Text style={styles.keyNodeLabel} numberOfLines={2}>{n.label}</Text>
                </View>
              ))}
              {aiSuggestion && (
                <View style={styles.aiSuggestionCard}>
                  <Text style={styles.aiSuggestionTopic}>{aiSuggestion.topic}</Text>
                  <Text style={styles.aiSuggestionAdvice} numberOfLines={3}>{aiSuggestion.advice}</Text>
                  <TouchableOpacity style={styles.speakBtn} onPress={() => speakTts(aiSuggestion.advice)}>
                    <Icon name="volume-high" size={14} color={Colors.primary} />
                    <Text style={styles.speakText}>朗读话术</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          )}
```

- `handleVoice`（L105-173）改为流式（替换 `readWavPcm` 一次性推流为 `connectAsrStreaming`）：

```tsx
      const wavPath = await stopRecording();
      const token = (await apiClient.getToken()) || '';
      const session = connectAsrStreaming(visitId, token, wavPath, {
        onSentence: (text, _final, speaker) => {
          setLiveText(text);
          if (speaker) setLiveSpeaker(speaker);
        },
        onCompliance: (blocked, violations) => {
          const alerts = mapComplianceViolations(violations);
          if (alerts.length) {
            setComplianceAlerts((prev) => [...prev, ...alerts]);
            const critical = alerts.find((a) => a.critical);
            if (critical) setShowRedLine(critical.description);
          }
        },
        onError: (msg) => {
          setLiveText('');
          setTranscribing(false);
          Alert.alert('语音转写', msg.includes('NLS') ? 'NLS 识别通道未配置，暂不可用' : msg);
        },
        onCompleted: async (fullText, speaker) => {
          asrSessionRef.current = null;
          setTranscribing(false);
          setLiveText('');
          setLiveSpeaker(undefined);
          if (fullText && fullText.trim()) {
            await addTranscript(fullText.trim(), speaker === 'doctor' ? 'hcp' : 'rep');
          }
        },
      });
      asrSessionRef.current = session;
```

（注意：`onReady` 不再需要（流式会话内部处理）；删除 `readWavPcm` 导入引用与 `CHUNK` 常量；`connectAsr` import 改为 `connectAsrStreaming`；文件头 import 区从 `../services/asr` 导入 `connectAsrStreaming`、从 `../services/recorder` 只保留 `startRecording`/`stopRecording`）

- styles（文件底部 StyleSheet）追加（配色沿用现有 Colors 语义）：

```ts
    keyNodeRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
    keyNodeBadge: { fontSize: 10, color: Colors.textWhite, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, marginRight: 6, overflow: 'hidden' },
    keyNodeDecision: { backgroundColor: '#1677ff' },
    keyNodeInterest: { backgroundColor: '#52c41a' },
    keyNodeLabel: { flex: 1, fontSize: 12, color: Colors.textPrimary },
    aiSuggestionCard: { backgroundColor: Colors.bgLight, borderRadius: 8, padding: 8, marginTop: 4 },
    aiSuggestionTopic: { fontSize: 12, fontWeight: '600', color: Colors.primary, marginBottom: 4 },
    aiSuggestionAdvice: { fontSize: 12, color: Colors.textPrimary, marginBottom: 6, lineHeight: 18 },
    speakBtn: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start' },
    speakText: { fontSize: 12, color: Colors.primary, marginLeft: 4 },
```

- [ ] **Step 3: ChatScreen 文案更新**

`mobile/src/screens/Chat/ChatScreen.tsx` L215-222 的 `handleVoice` 改为：

```tsx
  const handleVoice = useCallback(() => {
    // 语音转写绑定真实 visit_id（ASR WS 校验归属），聊天页无拜访上下文 → 仅提示入口
    Alert.alert('语音转写', '语音转写需在拜访流程中使用，请在拜访中页点击录音按钮。', [{ text: '知道了' }]);
  }, []);
```

- [ ] **Step 4: 契约测试补新字段用例**

`mobile/src/api/__tests__/api-contract.test.ts` 中 `mapTranscriptResult` 相关 describe 内追加：

```ts
  test('mapTranscriptResult 解析 LLM 推荐字段（key_nodes/ai_suggestion）', () => {
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

  test('mapTranscriptResult 缺推荐字段时容错为空', () => {
    const result = mapTranscriptResult({ transcript: 'x', objections: [], compliance: { violations: [] } });
    expect(result.key_nodes).toEqual([]);
    expect(result.ai_suggestion).toBeNull();
  });
```

（import 处补 `mapTranscriptResult`——若现有 import 已有则不动；测试文件已有 mapTranscriptResult 用例时并入同一 describe）

- [ ] **Step 5: 跑测试**

Run: `cd mobile && npx jest`
Expected: 60 passed

- [ ] **Step 6: TS 类型检查**

Run: `cd mobile && npx tsc --noEmit`
Expected: 无错误（若项目无此脚本或 tsconfig 限制，跳过并记录）

- [ ] **Step 7: 提交**

```bash
git add mobile/src/api/visit.ts mobile/src/screens/VisitInProgress/VisitInProgressScreen.tsx mobile/src/screens/Chat/ChatScreen.tsx mobile/src/api/__tests__/api-contract.test.ts
git commit -m "feat(mobile): 拜访中 AI 实时推荐区（关键节点+话术建议）+ 话术 TTS 朗读 + 流式转写接线"
```
