# Follow-up: web catch 留痕 + mobile ASR/TTS Robustness 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修掉四计划终审（fable, a39d4b87a190025f2）triage 命名的 8 项 Worth-fixing 遗留项：web 新增医生 catch 静默吞错补留痕；mobile asr.ts 三守卫（轮询重入/空块自旋/flush 串行化）+ tts.ts 两健壮性（NLS fetch 30s 超时、播放错误透传底层 err.message）+ tts 测试死代码清理；VisitInProgressScreen 双按双会话泄漏守卫。

**Architecture:** 全部为既有文件的局部加固，不新增模块、不改服务端（asr_ws.py 零改动）、不引入新依赖。asr.ts 用「轮询重入门禁 + flush 串行链 + 0 字节断推」三者互不干扰；tts.ts 沿用既有 epoch 代际门禁，只补 fetch 超时与错误透传；屏幕侧加一个同步 ref 守卫（与既有 recordingRef skip 逻辑互洽）。每项都有可判别测试（mutation-checked：删除修复实现则测试红）。

**Tech Stack:** TypeScript / React Native 0.75 / Jest / antd ProComponents（web）

## Global Constraints

- 实施方式：SDD 子代理流程，直接在 master 实施（用户既定模式）；每任务完成后 task review，全部完成后 fable 终审，最后推送 origin/master（用户既定批次模式：commit + push per batch）
- 降级铁律不变：LLM/TTS 失败绝不阻塞 transcript 主流程（屏幕侧已有 try/catch Alert，本计划不改该语义）
- asr.ts 既有语义不得破坏：OPEN 门禁、stopPending 延迟收尾、flushTo 无 stopped 门禁、finalizeStop 先 flush 后 stop 帧、epoch 代际门禁——回归测试必须全绿
- 测试基线：mobile jest 64（Task 2 后 67，Task 3 后 70）；web 无 jest 套件，验证门为 `cd web && npm run build`
- 服务端 asr_ws.py 零改动；不引入新依赖；提交信息用中文（既有风格）
- 屏幕侧无组件测试基建：Task 4 验证 = tsc + jest 回归 + 报告中枚举交错时序（沿用 T4 fix 惯例，reviewer 核验）

---
## Task 1: web DoctorList 新增医生 catch 补留痕

**Files:**
- Modify: `web/src/pages/Doctor/DoctorList.tsx:80-82`

**Interfaces:**
- Consumes: 无
- Produces: 无（catch 内新增 console.error，返回语义不变）

背景：终审 triage 项（web catch 静默吞错）。`onFinish` 的 catch 只有 `return false`——400-499 已由 client.ts 拦截器弹后端 message，但网络层错误（断网/超时）拦截器不弹，用户看到表单保留却无任何日志，排查困难。

- [ ] **Step 1: 修改 catch**

`web/src/pages/Doctor/DoctorList.tsx` L80-82 现为：

```tsx
          } catch {
            return false; // 400-499 已由 client.ts 拦截器弹后端 message，保留表单
          }
```

改为：

```tsx
          } catch (e) {
            // 400-499 已由 client.ts 拦截器弹后端 message；网络层错误（拦截器不弹）至少留痕
            console.error('新增医生失败', e);
            return false; // 保留表单
          }
```

- [ ] **Step 2: 构建验证**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add web/src/pages/Doctor/DoctorList.tsx
git commit -m "fix(web): 新增医生 catch 补 console.error 留痕（网络层错误不再静默）"
```

---
## Task 2: asr.ts 三守卫（轮询重入 / 空块自旋 / flush 串行化）+ 回归测试

**Files:**
- Modify: `mobile/src/services/asr.ts`（`connectAsrStreaming` 内）
- Test: `mobile/src/services/__tests__/asrStreaming.test.ts`

**Interfaces:**
- Consumes: 既有 `readPcmSource` / `pcmSourceLength`（recorder.ts）、`connectAsr` 内部会话
- Produces: 无签名变化（`connectAsrStreaming` 接口不变）；三个守卫均为模块内部实现

背景（三笔台账 minor）：
- **poll 重入门禁**（T2 minor）：`pollMs` 小于单轮耗时（RNFS 慢读）时，`setInterval` 回调可并发双推同一区间（两个 round 同时 pushSince）。修法：`pushing` 标志，round 入口 `if (pushing) return`。
- **空块自旋**（T2 minor）：`flushTo` 内部 `chunk.length === 0` break 后，`pushSince` 的 `while (offset < until && !stopped)` 重新进循环 → 同一 0 字节范围无限重试（busy 自旋至 stop）。修法：`flushTo` 返回「是否有进展」，`pushSince` 无进展即 break（下轮 poll 再试）。
- **flush 串行化**（FINAL minor）：`stop()` 的 `finalizeStop` flush 与在途轮询/start 初始 `pushSince` 并发 → 双 flush 双发同分片（offset 双重推进，可能尾损）。修法：`flushTail` Promise 链，所有 `flushTo` 入链串行执行（保持链存活：`flushTail = run.catch(() => {})`）。

- [ ] **Step 1: 写失败测试（三条，先红）**

在 `mobile/src/services/__tests__/asrStreaming.test.ts` 的 `describe('connectAsrStreaming')` 内追加（沿用既有 `openSession`/`flushTimers`/`settle` 工具与 MockWebSocket 模式）：

```ts
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
```

（关键：初始轮已把 10 字节推完（offset=until=10），若 stat 不增长，round 1 的 pushSince 循环根本不进 → read 不调用 → 挂起 mock 未被消费、断言失去判别力。stat 先长到 20 再挂起 read 才能卡住 round 1。判别点：round 2 不新增 stat/read 调用——删除 `pushing` 门禁则 round 2 会 stat+read（计数 3）→ 红。）

```ts
  test('空块自旋守卫：read 返回 0 字节时本轮终止，不无限重试', async () => {
    const { ws, session } = openSession();
    (RNFS.read as jest.Mock).mockResolvedValue(''); // 恒空读（0 字节）
    await settle();
    // 无守卫时 pushSince 会在同一 0 字节窗口内无限重试 read；有守卫时一轮只读一次
    expect((RNFS.read as jest.Mock).mock.calls.length).toBeLessThanOrEqual(2);
    session.stop(); // stop 后 finalize 同样应能收尾（0 字节 flush 直接跳过 → 发 stop 帧）
    await settle();
    const frames = ws.sent;
    expect(frames[frames.length - 1]).toBe(JSON.stringify({ type: 'stop' }));
  });
```

（判别点：read 调用次数有界。删除「flushTo 返回进展 / pushSince 无进展 break」则 read 在 settle 内无限增长 → 红。）

```ts
  test('flush 串行化：stop 与初始推流并发时不双发同分片', async () => {
    // 让 start 初始轮的首次 stat 挂起 → 期间 stop() → finalize 的 flush 与初始 flush 并发
    let resolveStat: (v: any) => void = () => {};
    const pendingStat = new Promise<any>((r) => { resolveStat = r; });
    const cbs = { onReady: jest.fn(), onSentence: jest.fn(), onCompliance: jest.fn(), onError: jest.fn(), onCompleted: jest.fn() };
    const session = connectAsrStreaming(1, 't', '/tmp/rec.wav', cbs);
    (RNFS.stat as jest.Mock).mockReturnValueOnce(pendingStat);
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    ws.onopen && ws.onopen(); // onReady → start → 初始轮 stat 挂起
    session.stop(); // stop 落在初始轮在途期间：finalizeStop 立即 stat（取 44+10）
    await settle();
    expect((RNFS.stat as jest.Mock).mock.calls.length).toBeGreaterThanOrEqual(2);
    resolveStat({ size: 44 + 10 }); // 放行初始轮
    await settle();
    const frames = ws.sent.filter((s) => s instanceof ArrayBuffer);
    // 串行化后：10 字节恰好发一次（无双发、无 offset 双重推进 → 无空窗）
    expect(frames.length).toBe(1);
    expect(Array.from(new Uint8Array(frames[0]))).toEqual(Array.from(pcmBuffer));
    expect(ws.sent[ws.sent.length - 1]).toBe(JSON.stringify({ type: 'stop' }));
  });
```

（判别点：二进制帧恰好 1 个且字节序完整。无串行链时初始 flush 与 finalize flush 双发同一分片 → 2 帧且重复 → 红。注意：`openSession` 不适用本测试（需要在 onopen 触发前替换首个 stat 返回值），按上述直接构造。）

- [ ] **Step 2: 跑测试确认三红**

Run: `cd mobile && npx jest src/services/__tests__/asrStreaming.test.ts`
Expected: 新 3 条 FAIL（旧 5 条 PASS）

- [ ] **Step 3: 实现三守卫**

`mobile/src/services/asr.ts` `connectAsrStreaming` 内改造（保持既有注释风格，中文注释）：

```ts
  const pollMs = opts.pollMs ?? 2000;
  const chunkSize = opts.chunkSize ?? 16 * 1024;
  let offset = 0; // 已推送的 PCM 字节偏移
  let timer: ReturnType<typeof setInterval> | null = null;
  let opened = false; // WS 已 open（onReady 已触发）；open 前禁止任何发送
  let stopped = false;
  let pushing = false; // 轮询重入门禁：上一轮未完成时跳过本轮（防并发双推同区间）
  // flush 串行链：所有 flushTo 入链执行，stop 收尾与轮询推流互斥（防双发同分片/offset 双重推进）
  let flushTail: Promise<void> = Promise.resolve();
```

`flushTo` 改为返回是否有进展，并上串行链：

```ts
  /** 推 [offset, until) 的 PCM 分片，不带 stopped 门禁（stop() 收尾 flush 专用）；返回是否有进展 */
  async function flushTo(until: number): Promise<boolean> {
    let progressed = false;
    const run = flushTail.then(async () => {
      while (offset < until) {
        const chunk = await readPcmSource(wavPath, offset, Math.min(chunkSize, until - offset));
        if (chunk.length === 0) break;
        session.sendAudioChunk(chunk);
        offset += chunk.length;
        progressed = true;
      }
    });
    flushTail = run.catch(() => {}); // 链保持存活；错误由调用方（pollRound/finalizeStop）兜底
    await run;
    return progressed;
  }
```

`pushSince` 加无进展即 break：

```ts
  async function pushSince(until: number) {
    while (offset < until && !stopped) {
      // 0 字节短读（录制文件 torn-read）→ 本轮不再重试，下一轮 poll 再试（防 busy 自旋）
      const progressed = await flushTo(Math.min(offset + chunkSize, until));
      if (!progressed) break;
    }
  }
```

轮询整轮包 `pushing` 门禁（替换 `start` 内的初轮与 `setInterval` 回调）：

```ts
  async function pollRound() {
    if (pushing) return; // 上一轮未完成：跳过本轮，不叠推
    pushing = true;
    try {
      const total = await pcmSourceLength(wavPath);
      await pushSince(total);
    } catch {
      // 读失败忽略，下一轮重试
    } finally {
      pushing = false;
    }
  }

  async function start() {
    await pollRound();
    if (stopped) return;
    timer = setInterval(() => {
      void pollRound();
    }, pollMs);
  }
```

（`finalizeStop` 不动——其 flushTo(total) 自动经串行链排队，先推完在途轮询再补推剩余 + stop 帧。）

- [ ] **Step 4: 跑测试确认三绿 + 全量回归**

Run: `cd mobile && npx jest src/services/__tests__/asrStreaming.test.ts`
Expected: 8 passed（旧 5 + 新 3）

Run: `cd mobile && npx jest`
Expected: 67 passed

- [ ] **Step 5: TS 类型检查**

Run: `cd mobile && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 6: mutation 自查**

对三守卫各自删除实现后重跑测试，确认对应测试变红（报告里记录结果）。

- [ ] **Step 7: 提交**

```bash
git add mobile/src/services/asr.ts mobile/src/services/__tests__/asrStreaming.test.ts
git commit -m "fix(mobile): asr 流式推流三守卫——轮询重入门禁/空块自旋终止/flush 串行链"
```

---
## Task 3: tts.ts fetch 30s 超时 + 播放错误透传底层 err.message + 测试死代码清理

**Files:**
- Modify: `mobile/src/services/tts.ts`
- Test: `mobile/src/services/__tests__/tts.test.ts`

**Interfaces:**
- Consumes: 无新依赖（AbortController RN 内置）
- Produces: 无签名变化（`speak`/`stopSpeaking`/`getTtsToken` 不变；超时抛 `Error('语音合成请求超时（30s）')`，调用方既有 Alert 捕获）

背景（三笔台账 minor）：
- **NLS fetch 无超时**（T3 minor）：client.ts 惯例 30s AbortController；挂起的 NLS 合成请求会让 speak 永挂起。修法：fetch 带 `{ signal }` + 30s 定时 abort；catch 中 `controller.signal.aborted` 判定超时（不依赖 reject 错误的 name——RN 各环境 abort 错误形状不一）。
- **播放错误丢底层 err.message**（T3 minor）：`reject(new Error('音频播放初始化失败'))` 裸错误，真机难诊断。修法：拼接 `err.message`。
- **stopSpeaking 测试死代码**（T3 minor）：`(global as any).__ttsCurrent = s` 写全局但模块不读，断言 nothing（删除实现也绿）。修法：真实路径驱动 `current`（await speak 后 current 置位，stopSpeaking 后断言 stop/release 被调）——需在 Sound mock 工厂暴露 `__mockStop`。

- [ ] **Step 1: 写失败测试（先红）**

`mobile/src/services/__tests__/tts.test.ts`：

a) Sound mock 工厂补 `__mockStop` 暴露（L9-23 内）：

```ts
  const SoundMock = jest.fn().mockImplementation((_path: string, _base: string, cb: (e: Error | null) => void) => {
    setTimeout(() => cb(null), 0);
    return { play: mockPlay, release: mockRelease, stop: mockStop };
  });
  (SoundMock as any).__mockPlay = mockPlay;
  (SoundMock as any).__mockRelease = mockRelease;
  (SoundMock as any).__mockStop = mockStop;
```

b) 删除「stopSpeaking 释放当前播放」死代码测试（L108-112，`(global as any).__ttsCurrent = s;` 写全局但模块不读、断言 nothing——删除实现也绿），改为真实路径测试：

```ts
  // 真实路径驱动 current：await speak 完成后 current 已置位（play 完成回调被 mock 挂起不触发）
  // 位置必须在「speak 合成 URL 带 appkey/token/text 并写文件播放」用例之前（L87）——
  // Sound mock 的 stop/release 是模块级共享 jest.fn，若其后的 speak 成功用例先跑，
  // 其 executor 的 stopCurrent() 会先 stop 掉本测试残留实例，计数被污染；
  // 本测试以 stopSpeaking 收尾（current 置 null），不污染其后的 speak 成功用例
  test('stopSpeaking 打断正在播放的 sound（stop + release）', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: async () => new Uint8Array([1, 2]).buffer,
    }) as any;
    const SoundMock = Sound as unknown as jest.Mock & { __mockPlay: jest.Mock; __mockRelease: jest.Mock; __mockStop: jest.Mock };
    await speak('主任您好');
    stopSpeaking();
    expect(SoundMock.__mockStop).toHaveBeenCalledTimes(1);
    expect(SoundMock.__mockRelease).toHaveBeenCalledTimes(1);
  });
```

（新测试断言真实行为：stopSpeaking 后正在播放的实例被 stop + release。若 shared mock 的累计计数非 1 → 说明 current 被前置用例污染 → 排查顺序。原死代码测试删除，`__ttsCurrent` 全局不再存在。）

c) 追加超时与错误透传用例：

```ts
  test('NLS 合成请求 30s 无响应 → 超时报错', async () => {
    jest.useFakeTimers();
    try {
      (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
      // fetch 永不 resolve，只监听 abort 后 reject（模拟 RN 挂起请求被 AbortController 取消）
      global.fetch = jest.fn().mockImplementation(
        (_url: string, opts?: { signal?: AbortSignal }) =>
          new Promise((_resolve, reject) => {
            opts?.signal?.addEventListener('abort', () => reject(new Error('Aborted')));
          }),
      ) as any;
      const p = speak('x');
      jest.advanceTimersByTime(30_000);
      await expect(p).rejects.toThrow('超时');
    } finally {
      jest.useRealTimers();
    }
  });

  test('合成请求网络错误原样上抛（不被超时包裹吞掉）', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    global.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed')) as any;
    await expect(speak('x')).rejects.toThrow('Network request failed');
  });

  test('播放初始化失败透传底层 err.message', async () => {
    (apiClient.request as jest.Mock).mockResolvedValue({ token: 't', appkey: 'a' });
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      arrayBuffer: async () => new Uint8Array([1, 2]).buffer,
    }) as any;
    // 本用例内 Sound 加载回调改报错
    const origImpl = (Sound as unknown as jest.Mock).getMockImplementation();
    (Sound as unknown as jest.Mock).mockImplementationOnce(
      (_path: string, _base: string, cb: (e: Error | null) => void) => {
        setTimeout(() => cb(new Error('file not found')), 0);
        return { play: jest.fn(), release: jest.fn(), stop: jest.fn() };
      },
    );
    try {
      await expect(speak('x')).rejects.toThrow('file not found');
    } finally {
      (Sound as unknown as jest.Mock).mockImplementation(origImpl as any);
    }
  });
```

- [ ] **Step 2: 跑测试确认红**

Run: `cd mobile && npx jest src/services/__tests__/tts.test.ts`
Expected: 新用例 FAIL（无超时实现 → 永挂；无透传 → 收不到 file not found）

- [ ] **Step 3: 实现 tts.ts 两处修改**

`mobile/src/services/tts.ts` `speak` 内，fetch 段（现 L35-37）改为：

```ts
  const url = `${TTS_URL}?appkey=${encodeURIComponent(appkey)}&token=${encodeURIComponent(token)}&text=${encodeURIComponent(text)}&format=wav&sample_rate=16000`;
  // 30s 超时（client.ts 惯例）：NLS 挂起不能让 speak 永挂；超时判定用 signal.aborted
  //（不依赖 reject 错误的 name——RN 各环境 abort 错误形状不一）
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  let resp: Response;
  try {
    resp = await fetch(url, { signal: controller.signal });
  } catch (e) {
    if (controller.signal.aborted) throw new Error('语音合成请求超时（30s）');
    throw e;
  } finally {
    clearTimeout(timeout);
  }
```

播放初始化失败（现 L61）改为透传：

```ts
      if (err) {
        reject(new Error(`音频播放初始化失败：${err.message}`));
        return;
      }
```

- [ ] **Step 4: 跑测试确认全绿**

Run: `cd mobile && npx jest src/services/__tests__/tts.test.ts`
Expected: 11 passed（原 7 + 新增 3 + 重写 1）

Run: `cd mobile && npx jest`
Expected: 70 passed

- [ ] **Step 5: TS 类型检查**

Run: `cd mobile && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 6: mutation 自查**

去掉超时 try/catch → 超时用例红；去掉 err.message 拼接 → 透传用例红；报告记录。

- [ ] **Step 7: 提交**

```bash
git add mobile/src/services/tts.ts mobile/src/services/__tests__/tts.test.ts
git commit -m "fix(mobile): tts NLS 合成请求 30s 超时 + 播放初始化错误透传底层信息 + 测试死代码清理"
```

---
## Task 4: VisitInProgressScreen 双按双会话泄漏守卫

**Files:**
- Modify: `mobile/src/screens/VisitInProgress/VisitInProgressScreen.tsx`

**Interfaces:**
- Consumes: 既有 `recordingRef` skip 逻辑（press 分支 getToken 后检查）、`asrSessionRef`
- Produces: 无（新增内部 ref `pressInFlightRef`）

背景（T4 minor，终审 triage Worth-fixing）：**双按双会话泄漏**——两次 tap 都落进 `await startRecording()` 的异步窗口内（此时 `transcribing` 仍 false，双按均可进入 press 分支；`recordingRef` 检查发生在各自 getToken 之后，两链都通过）→ 双双 `connectAsrStreaming`，`asrSessionRef.current` 只留最后一个 → 前一会话的 WS + 服务端 receive 循环泄漏至卸载。

修法：press 入口同步置位 `pressInFlightRef`，已置位则忽略本次（双按守卫）；在「建链完成 / 弃建 / 建链失败 / release」四处清理。与既有逻辑的互洽性（必需保持）：

- press 分支既有 `recordingRef.current` 检查（快按快放弃建）**保留不动**——守卫只管「同一时刻只有一条 press 链在途」，不替代 skip 语义
- release 分支既有 `recordingRef.current = false` 同步置位保留；守卫在其后同点清理
- release 后 `transcribing=true` 已挡后续 press（既有行为，本守卫不破坏）；双按守卫只挡「release 之前」的第二 tap

- [ ] **Step 1: 声明守卫 ref**

`mobile/src/screens/VisitInProgress/VisitInProgressScreen.tsx` L51 `recordingRef` 声明旁（L50-51 附近）追加：

```tsx
  const recordingRef = useRef(false); // recording 状态的 ref 镜像，供卸载清理读取
  const pressInFlightRef = useRef(false); // 双按守卫：一次按下只允许一条 press 链（防双会话泄漏）
```

- [ ] **Step 2: press 分支加守卫**

`handleVoice`（L124-189）press 分支改三处：

a) L125-126 入口（`if (!recording)` 块内第一行）前加：

```tsx
  const handleVoice = useCallback(async () => {
    if (transcribing) return;
    if (!recording) {
      // 双按守卫：前一次按下仍在建链途中（startRecording/getToken 未完成）→ 忽略本次，
      // 否则两条 press 链都会通过 recordingRef 检查 → 双会话，ref 只留最后一个 → 前会话泄漏
      if (pressInFlightRef.current) return;
      pressInFlightRef.current = true;
      try {
        await startRecording();
      } catch (e: any) {
        pressInFlightRef.current = false; // 录音启动失败：本次 press 终结
        Alert.alert('提示', '无法开始录音：' + (e.message || '麦克风不可用'));
        return;
      }
```

b) 既有「快按快放弃建」分支（L141-144，`if (!recordingRef.current)`）内补清理：

```tsx
        if (!recordingRef.current) {
          pressInFlightRef.current = false; // 弃建：本次 press 终结
          setTranscribing(false); // 复位 release 分支挂起的转写态（无会话 → 不会有 completed 帧）
          return;
        }
```

c) 会话建立成功、赋 ref 之后（L179 `asrSessionRef.current = session;` 之后）补清理：

```tsx
        asrSessionRef.current = session;
        pressInFlightRef.current = false; // 会话已建立：本次 press 终结
```

d) 既有 catch（L180-188 建链失败回滚）内补清理（`setTranscribing(false)` 旁）：

```tsx
      } catch (e: any) {
        // 会话建立失败（token 通道异常等）：回滚录音态，避免"停止录音"按钮但无会话可 stop 的悬空态；
        // 若 release 已先行（快按快放），此处同样复位转写态（无会话 → 不会有 completed 帧）
        pressInFlightRef.current = false; // 本次 press 终结
        setTranscribing(false);
        setRecording(false);
        recordingRef.current = false;
        stopRecording().catch(() => {});
        Alert.alert('提示', '转写通道启动失败：' + (e.message || '请重试'));
      }
```

- [ ] **Step 3: release 分支清理**

release 分支（L190-204，`}` 之后 `setRecording(false); recordingRef.current = false;` 处）与 `recordingRef.current = false` 同点补：

```tsx
    setRecording(false);
    recordingRef.current = false;
    pressInFlightRef.current = false; // 同步清理：release 后允许新的 press 链（transcribing 已挡新按）
    setTranscribing(true);
```

（注意：release 后 press 入口被 `transcribing` 挡住，此清理主要是状态卫生 + 防「release → 旧链残留」时守卫误卡下一次。）

- [ ] **Step 4: 全量回归 + 类型检查**

Run: `cd mobile && npx jest`
Expected: 70 passed（无新测试——屏幕无组件测试基建，回归即验证）

Run: `cd mobile && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 5: 报告要求：交错时序穷举**

报告须枚举全部交错时序并说明每个序不被破坏（沿用 T4 fix round 惯例）：
1. 单按 → 正常建链 → release → 收尾（守卫生命周期完整）
2. 双按（第二 tap 落在 `await startRecording()` 窗口内）→ 第二 tap 被守卫忽略 → 只有一条链 → 单会话
3. 快按快放（release 落在 getToken 窗口内）→ press 弃建 + 守卫清理 → transcribing 复位
4. 双按 + 快放（第二 tap 被守卫挡，release 已同步清 guard/recordingRef）→ 弃建路径
5. 建链失败（getToken 抛错）→ catch 清理 guard + 回滚录音态 → 可再次 press
6. 连续正常两轮（press→release→press）：守卫释放后第二轮的 press 正常进入

- [ ] **Step 6: 提交**

```bash
git add mobile/src/screens/VisitInProgress/VisitInProgressScreen.tsx
git commit -m "fix(mobile): 拜访中录音双按双会话泄漏守卫（press 入口同步防重入）"
```
