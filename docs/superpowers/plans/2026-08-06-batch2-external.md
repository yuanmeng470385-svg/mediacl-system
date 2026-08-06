# 批次 2：外部服务接入批 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 短信通道接入阿里云 dysmsapi（代码就绪 + 配置位，不真发）；mobile 录音能力全量落地（双端权限 + 录音库 + ASR WS 客户端 + ChatScreen 接线），识别走 visit-service 现成 NLS 链路（无 appkey 时 fail-closed 提示）。

**Architecture:** auth-service 的 AliyunSmsSender 从抛错占位改为真 dysmsapi 调用（签名/模板 CODE 缺则抛清晰错误，保持 fail-fast）；mobile 端用 react-native-audio-record 录 WAV(16k/16bit/mono)，react-native-fs 读文件分片推 visit-service 的 `/ws/visits/{visit_id}/asr?token=JWT`（直连 8002，网关不代理 WS），sentence 帧流式回填对话输入框。

**Tech Stack:** Python 3 + alibabacloud_dysmsapi20170525（auth-service）；React Native 0.75 + react-native-audio-record + react-native-fs + RN 内置 WebSocket（mobile）。

## Global Constraints

- 无短信凭证（签名/模板 CODE）→ 代码就绪即可，**不真发短信**；无 NLS_APPKEY → 录音端全做，识别服务端 fail-closed（error 帧 → 前端提示"NLS 未配置"，不产生假文本）。
- 后端 visit-service 零改动（NLS 链路已完整：realtime_asr.py + asr_ws.py）。
- 录音流只能"录完再推"（react-native-audio-record 无流式回调）：stop 后读文件跳过 44 字节 WAV 头分片推送——体验为"录音→转写"，不做实时字幕（YAGNI）。
- 新依赖必须进入 package.json 的 dependencies；Android 权限加 `RECORD_AUDIO`，iOS 加 `NSMicrophoneUsageDescription`。
- Android 模拟器无麦克风：录音链路验证 = jest 单测（asr.ts 协议）+ android 构建通过；真机录音为可选手工步骤。
- 后端测试：`cd services/<s> && python -m pytest -q`。mobile 测试：`cd mobile && npx jest`。
- commit 惯例：`fix(scope): 描述` / `feat(scope): 描述`，结尾 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`，本地不 push。

---

### Task 1: auth-service — 短信配置项 + 依赖

**Files:**
- Modify: `services/auth-service/app/config.py`（加 3 个配置项）
- Modify: `services/auth-service/requirements.txt`（加 SDK）
- Modify: `.env.example`（加配置位说明）

**Interfaces:**
- Produces: `settings.SMS_SIGN_NAME` / `settings.SMS_TEMPLATE_CODE`（str，缺省空串）、`settings.SMS_PROVIDER`（已有）；requirements 新增 `alibabacloud_dysmsapi20170525`。

- [ ] **Step 1: config.py 加配置项**

`services/auth-service/app/config.py` 的短信段（:26-28）改为：

```python
    # --- 短信通道 ---
    # console（默认，只写日志）/ aliyun（需签名与模板 CODE）
    SMS_PROVIDER = os.getenv("AUTH_SMS_PROVIDER", "console")
    SMS_SIGN_NAME = os.getenv("AUTH_SMS_SIGN_NAME", "")
    SMS_TEMPLATE_CODE = os.getenv("AUTH_SMS_TEMPLATE_CODE", "")
```

- [ ] **Step 2: requirements.txt 加依赖**

`services/auth-service/requirements.txt` 追加：

```
alibabacloud_dysmsapi20170525>=3.1.0
```

（dysmsapi SDK 传递依赖 alibabacloud_tea_openapi，无需显式加。）

- [ ] **Step 3: .env.example 加配置位**

`.env.example` 短信段追加：

```
AUTH_SMS_SIGN_NAME=            # 阿里云短信签名（如"某某医药"），配齐后 AUTH_SMS_PROVIDER=aliyun 生效
AUTH_SMS_TEMPLATE_CODE=        # 阿里云短信模板 CODE（如 SMS_123456789），变量名用 code
```

- [ ] **Step 4: 验证安装**

Run: `cd "/d/gongsi/medical system" && pip install -r services/auth-service/requirements.txt`
Expected: 安装成功（网络需可达 pypi；不可达时注明依赖待装，代码先行）。

- [ ] **Step 5: Commit**

```bash
cd "/d/gongsi/medical system" && git add services/auth-service .env.example && git commit -m "feat(auth): 短信配置项与 dysmsapi SDK 依赖
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: auth-service — AliyunSmsSender 真实现（TDD）

**Files:**
- Modify: `services/auth-service/app/services/sms.py`（AliyunSmsSender 替换占位）
- Create: `services/auth-service/tests/test_sms.py`

**Interfaces:**
- Consumes: `settings.SMS_SIGN_NAME` / `SMS_TEMPLATE_CODE`（Task 1）；现有 `SmsSender.send_code(phone, code)` 抽象（调用方 auth.py:105 不动）
- Produces: `AliyunSmsSender` 真实现——构造时校验配置缺失抛 `SmsSendError`；`send_code` 调 dysmsapi SendSms，非 OK 抛 `SmsSendError`。

- [ ] **Step 1: 写失败测试**

```python
# services/auth-service/tests/test_sms.py
"""AliyunSmsSender 真实现测试（mock dysmsapi 客户端，不真发短信）"""
import pytest
from app.services.sms import AliyunSmsSender, SmsSendError


class FakeResponse:
    def __init__(self, code: str, message: str = ""):
        self.body = type("Body", (), {"code": code, "message": message})


class FakeClient:
    def __init__(self, code: str = "OK"):
        self.code = code
        self.last_req = None

    def send_sms(self, req):
        self.last_req = req
        return FakeResponse(self.code)


def test_aliyun_sender_缺配置抛错(monkeypatch):
    monkeypatch.setattr("app.config.settings.SMS_SIGN_NAME", "")
    monkeypatch.setattr("app.config.settings.SMS_TEMPLATE_CODE", "")
    with pytest.raises(SmsSendError):
        AliyunSmsSender()


def test_aliyun_sender_签名缺失抛错(monkeypatch):
    monkeypatch.setattr("app.config.settings.SMS_SIGN_NAME", "")
    monkeypatch.setattr("app.config.settings.SMS_TEMPLATE_CODE", "SMS_123")
    with pytest.raises(SmsSendError):
        AliyunSmsSender()


def test_aliyun_sender_发送成功(monkeypatch):
    monkeypatch.setattr("app.config.settings.SMS_SIGN_NAME", "测试签名")
    monkeypatch.setattr("app.config.settings.SMS_TEMPLATE_CODE", "SMS_123")
    fake = FakeClient()
    monkeypatch.setattr(AliyunSmsSender, "_make_client", lambda self: fake)
    sender = AliyunSmsSender()
    sender.send_code("13800138000", "123456")
    req = fake.last_req
    assert req.phone_numbers == "13800138000"
    assert req.sign_name == "测试签名"
    assert req.template_code == "SMS_123"
    assert req.template_param == '{"code": "123456"}'


def test_aliyun_sender_业务失败抛错(monkeypatch):
    monkeypatch.setattr("app.config.settings.SMS_SIGN_NAME", "测试签名")
    monkeypatch.setattr("app.config.settings.SMS_TEMPLATE_CODE", "SMS_123")
    fake = FakeClient(code="isv.MOBILE_NUMBER_ILLEGAL")
    monkeypatch.setattr(AliyunSmsSender, "_make_client", lambda self: fake)
    sender = AliyunSmsSender()
    with pytest.raises(SmsSendError):
        sender.send_code("13800138000", "123456")
```

Run: `cd services/auth-service && python -m pytest tests/test_sms.py -v`
Expected: FAIL（AliyunSmsSender 无 `_make_client`、抛错文案不同）。

- [ ] **Step 2: 真实现**

`services/auth-service/app/services/sms.py` 的 AliyunSmsSender 替换为：

```python
class AliyunSmsSender(SmsSender):
    """阿里云短信（dysmsapi）——真实通道。

    前置配置（缺一个都不能发，构造时即抛错，fail-fast）：
        AUTH_SMS_SIGN_NAME     短信签名
        AUTH_SMS_TEMPLATE_CODE 模板 CODE（形如 SMS_123456789）
        复用现有 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET
    模板变量固定为 {"code": "..."}——申请模板时变量名请命名为 code。
    """

    def __init__(self):
        from app.config import settings
        sign_name = settings.SMS_SIGN_NAME.strip()
        template_code = settings.SMS_TEMPLATE_CODE.strip()
        missing = []
        if not sign_name:
            missing.append("AUTH_SMS_SIGN_NAME")
        if not template_code:
            missing.append("AUTH_SMS_TEMPLATE_CODE")
        if missing:
            raise SmsSendError(
                f"阿里云短信通道配置缺失: {' / '.join(missing)}。"
                "补齐后重试，或把 AUTH_SMS_PROVIDER 设回 console。"
            )
        self._sign_name = sign_name
        self._template_code = template_code
        self._client = self._make_client()

    def _make_client(self):
        """创建 dysmsapi 客户端。独立方法便于测试注入。"""
        import os
        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_tea_openapi import models as open_api_models

        access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
        access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
        if not access_key_id or not access_key_secret:
            raise SmsSendError(
                "阿里云短信通道缺少 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET"
            )
        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id="cn-hangzhou",  # dysmsapi 固定接入地域
        )
        return Client(config)

    def send_code(self, phone: str, code: str) -> None:
        import json
        from alibabacloud_dysmsapi20170525 import models as dysmsapi_models

        request = dysmsapi_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=self._sign_name,
            template_code=self._template_code,
            template_param=json.dumps({"code": code}, ensure_ascii=False),
        )
        try:
            response = self._client.send_sms(request)
        except Exception as e:  # SDK 网络/签名错误
            raise SmsSendError(f"阿里云短信发送失败: {e}") from e
        if response.body.code != "OK":
            raise SmsSendError(
                f"阿里云短信发送失败 [{response.body.code}]: {response.body.message}"
            )
```

- [ ] **Step 3: 跑测试**

Run: `cd services/auth-service && python -m pytest tests/test_sms.py -v`
Expected: 4 passed。

- [ ] **Step 4: 全量回归**

Run: `cd services/auth-service && python -m pytest -q`
Expected: 全部通过（既有 test_auth.py 用 RecordingSender，不受影响）。

- [ ] **Step 5: Commit**

```bash
cd "/d/gongsi/medical system" && git add services/auth-service && git commit -m "feat(auth): AliyunSmsSender 真实现（dysmsapi，缺配置 fail-fast）
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: mobile — 录音依赖 + 双端权限

**Files:**
- Modify: `mobile/package.json`（加 react-native-audio-record、react-native-fs）
- Modify: `mobile/android/app/src/main/AndroidManifest.xml`（RECORD_AUDIO）
- Modify: `mobile/ios/medagentmobile/Info.plist`（NSMicrophoneUsageDescription）

- [ ] **Step 1: 装依赖**

Run: `cd mobile && npm install react-native-audio-record react-native-fs`
Expected: 装进 dependencies（确认 package.json 出现 `"react-native-audio-record": "^0.6.2"` 与 `"react-native-fs": "^2.20.0"` 级别条目）。若 npm 网络不可达（需代理），记录并改用 `npm install --registry=https://registry.npmmirror.com` 重试。

- [ ] **Step 2: Android 权限**

`mobile/android/app/src/main/AndroidManifest.xml` 在 `<uses-permission android:name="android.permission.INTERNET"/>` 后加：

```xml
<uses-permission android:name="android.permission.RECORD_AUDIO"/>
```

- [ ] **Step 3: iOS 权限文案**

`mobile/ios/medagentmobile/Info.plist` 的 dict 内加：

```xml
<key>NSMicrophoneUsageDescription</key>
<string>用于语音提问与拜访录音转写</string>
```

- [ ] **Step 4: 验证 Android 构建（不装模拟器，仅编译）**

Run: `cd mobile/android && ./gradlew assembleDebug -q`
Expected: BUILD SUCCESSFUL（若 react-native-audio-record 老库在 RN 0.75 链接失败，记录错误并检查 autolinking 是否生效——`./gradlew :app:dependencies` 查依赖树）。构建超时允许 600s；Gradle 首次构建可能需代理。

- [ ] **Step 5: Commit**

```bash
cd "/d/gongsi/medical system" && git add mobile && git commit -m "feat(mobile): 录音库与双端麦克风权限
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: mobile — asr.ts ASR WS 客户端 + 单测

**Files:**
- Create: `mobile/src/services/asr.ts`
- Create: `mobile/src/services/__tests__/asr.test.ts`

**Interfaces:**
- Consumes: `apiClient.getToken()`（异步拿 JWT，`mobile/src/api/client.ts:37-41`）
- Produces:
  - `connectAsr(visitId: number, token: string, cbs: AsrCallbacks): AsrSession`
  - `AsrCallbacks`: `onReady(): void`、`onSentence(text: string, final: boolean): void`、`onCompliance(blocked: boolean, violations: unknown[]): void`、`onError(msg: string): void`、`onCompleted(fullText: string): void`（fullText = 最后一次 final sentence 文本，可能为空）
  - `AsrSession`: `sendAudioChunk(chunk: Uint8Array): void`、`stop(): void`、`close(): void`
  - 内部：直连 `ws://10.0.2.2:8002/ws/visits/{visitId}/asr?token=<JWT>`（Platform android）/ `ws://localhost:8002/...`（ios），Binary 帧 = PCM(16k/16bit/mono)，Text 帧 = `{"type":"stop"}`；内部累计 `finalText`（每次 final sentence 覆盖），completed 时回传。

- [ ] **Step 1: 写失败测试（mock 全局 WebSocket）**

```ts
// mobile/src/services/__tests__/asr.test.ts
import { connectAsr } from '../asr';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((e: any) => void) | null = null;
  onclose: (() => void) | null = null;
  sent: any[] = [];
  readyState = 0;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
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
```

Run: `cd mobile && npx jest services/__tests__/asr`
Expected: FAIL（`asr.ts` 不存在，模块解析错误）。

- [ ] **Step 2: 实现 asr.ts**

```ts
/**
 * ASR（语音转写）WebSocket 客户端
 *
 * 直连 visit-service 的 /ws/visits/{visit_id}/asr（网关不代理 WS）：
 *   - 客户端→服务端：Binary = PCM 音频分片（16k/16bit/单声道）；Text = {"type":"stop"}
 *   - 服务端→客户端：ready / sentence(index,text,final) / compliance(blocked,violations) / error / completed
 */
import { Platform } from 'react-native';

const ASR_HOST = Platform.select({
  android: '10.0.2.2:8002',
  ios: 'localhost:8002',
  default: 'localhost:8002',
});

export interface AsrCallbacks {
  onReady: () => void;
  onSentence: (text: string, final: boolean) => void;
  onCompliance: (blocked: boolean, violations: unknown[]) => void;
  onError: (message: string) => void;
  /** completed 帧：回传最后一次 final sentence 的全量文本（可能为空） */
  onCompleted: (fullText: string) => void;
}

export interface AsrSession {
  sendAudioChunk(chunk: Uint8Array): void;
  stop(): void;
  close(): void;
}

export function connectAsr(visitId: number, token: string, cbs: AsrCallbacks): AsrSession {
  const ws = new WebSocket(`ws://${ASR_HOST}/ws/visits/${visitId}/asr?token=${encodeURIComponent(token)}`);
  let finalText = '';

  ws.onopen = () => cbs.onReady();
  ws.onmessage = (e) => {
    try {
      const frame = JSON.parse(e.data as string);
      switch (frame.type) {
        case 'sentence':
          cbs.onSentence(frame.text ?? '', !!frame.final);
          if (frame.final) finalText = frame.text ?? '';
          break;
        case 'compliance':
          cbs.onCompliance(!!frame.blocked, frame.violations ?? []);
          break;
        case 'error':
          cbs.onError(frame.message || '语音转写失败');
          break;
        case 'completed':
          cbs.onCompleted(finalText);
          ws.close();
          break;
        default:
          break;
      }
    } catch {
      // 非 JSON 帧忽略
    }
  };
  ws.onerror = () => cbs.onError('语音服务连接失败');

  return {
    sendAudioChunk(chunk: Uint8Array) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(chunk.buffer.slice(chunk.byteOffset, chunk.byteOffset + chunk.byteLength) as ArrayBuffer);
      }
    },
    stop() {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop' }));
      }
    },
    close() {
      ws.close();
    },
  };
}
```

（签名用 `connectAsr(visitId, token, cbs)` 与测试一致；Task 5 中调用侧先 `await apiClient.getToken()`。）

- [ ] **Step 3: 跑测试**

Run: `cd mobile && npx jest services/__tests__/asr`
Expected: 5 passed。

- [ ] **Step 4: 类型检查 + Commit**

Run: `cd mobile && npx tsc --noEmit`
Expected: PASS。

```bash
cd "/d/gongsi/medical system" && git add mobile/src/services && git commit -m "feat(mobile): ASR WS 客户端（帧协议 + 单测）
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: mobile — 拜访页真实录音接线 + ChatScreen 语音入口

**Files:**
- Create: `mobile/src/services/recorder.ts`（录音封装，独立便于替换）
- Modify: `mobile/src/screens/VisitInProgress/VisitInProgressScreen.tsx`（底部栏加录音按钮，走 ASR WS）
- Modify: `mobile/src/screens/Chat/ChatScreen.tsx:207-209`（voiceBtn 接 onPress）

**Interfaces:**
- Consumes: `connectAsr(visitId, token, cbs)`（Task 4）、`apiClient.getToken()`、`react-native-audio-record`、`react-native-fs`
- Produces: `recorder.ts` 的 `startRecording(): Promise<void>`、`stopRecording(): Promise<string>`（返回 wav 路径）、`readWavPcm(path): Promise<Uint8Array>`（跳过 44 字节头）

接线决策：ASR WS 端点要求真实 visit_id（asr_ws.py 校验 visit 存在 → 4404）。**完整录音→转写接线放在 VisitInProgressScreen**（有 visitId，转写结果走现有 addTranscript → 异议/合规检测 → transcript 落库），这是 NLS_APPKEY 配好后即可用的真实场景；ChatScreen 无拜访上下文，语音按钮接提示（避免伪造 visit）。

- [ ] **Step 1: 写 recorder.ts**

```ts
/**
 * 录音封装（react-native-audio-record 录制 WAV 16k/16bit/mono，与 ASR 协议一致）
 */
import AudioRecord from 'react-native-audio-record';
import RNFS from 'react-native-fs';

const RECORD_OPTIONS = {
  sampleRate: 16000,
  channels: 1,
  bitsPerSample: 16,
  wavFile: 'medagent_rec.wav',
  audioSource: 1, // Android MIC
};

export async function startRecording(): Promise<void> {
  AudioRecord.init(RECORD_OPTIONS);
  AudioRecord.start();
}

export async function stopRecording(): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    AudioRecord.stop()
      .then((path: string) => resolve(path))
      .catch(reject);
  });
}

/** 读 wav 文件，跳过 44 字节头，返回 PCM 数据 */
export async function readWavPcm(path: string): Promise<Uint8Array> {
  const base64 = await RNFS.readFile(path, 'base64');
  const binary = atob(base64);
  const raw = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) raw[i] = binary.charCodeAt(i);
  const HEADER = 44;
  return raw.length > HEADER ? raw.subarray(HEADER) : new Uint8Array(0);
}
```

（若 TS 对 `atob` 报类型错误，文件头加 `declare const atob: (s: string) => string;`。）

- [ ] **Step 2: VisitInProgress 底部栏加录音按钮**

`VisitInProgressScreen.tsx`：
- import 加：`connectAsr`（`../../services/asr`）、`startRecording`/`stopRecording`/`readWavPcm`（`../../services/recorder`）、`apiClient`（`../../api/client`）
- 状态：

```tsx
const [recording, setRecording] = useState(false);
const [transcribing, setTranscribing] = useState(false);
const [liveText, setLiveText] = useState('');           // 转写增量文本（onSentence 更新）
const asrSessionRef = useRef<ReturnType<typeof connectAsr> | null>(null);
```

- 录音处理（模拟按钮保留，加真实录音按钮）：

```tsx
const handleVoice = useCallback(async () => {
  if (transcribing) return;
  if (!recording) {
    try {
      await startRecording();
      setRecording(true);
    } catch (e: any) {
      Alert.alert('提示', '无法开始录音：' + (e.message || '麦克风不可用'));
    }
    return;
  }
  // 停止录音 → 推流转写
  setRecording(false);
  setTranscribing(true);
  try {
    const wavPath = await stopRecording();
    const pcm = await readWavPcm(wavPath);
    if (pcm.length === 0) { Alert.alert('提示', '未检测到有效录音'); return; }
    const token = (await apiClient.getToken()) || '';
    const CHUNK = 16 * 1024;
    const session = connectAsr(visitId, token, {
      onReady: () => {
        for (let i = 0; i < pcm.length; i += CHUNK) {
          session.sendAudioChunk(pcm.subarray(i, i + CHUNK));
        }
        session.stop();
      },
      // 增量句：转写进行中在底部栏上方显示一行"转写中：<当前文本>"
      onSentence: (text) => setLiveText(text),
      onCompliance: () => {},
      onError: (msg) => {
        setLiveText('');
        Alert.alert('语音转写', msg === 'NLS 未配置' ? 'NLS 识别通道未配置，暂不可用' : msg);
      },
      onCompleted: async (fullText) => {
        asrSessionRef.current = null;
        setTranscribing(false);
        setLiveText('');
        if (fullText && fullText.trim()) {
          await addTranscript(fullText.trim(), 'rep'); // 走异议/合规检测 + 落库
        }
      },
    });
    asrSessionRef.current = session;
  } catch (e: any) {
    setTranscribing(false);
    Alert.alert('提示', '转写失败：' + (e.message || '请重试'));
  }
}, [recording, transcribing, visitId, addTranscript]);
```

注意：本任务**扩展 asr.ts 的 onCompleted 回调签名**为 `onCompleted: (fullText: string) => void`（服务端 completed 帧后随文本帧一起到达的语义：服务端在断开前会发 `{"type":"completed"}`，全量文本以最后一次 final sentence 为准——实现时 asr.ts 内部累计 final 句，completed 时把累计文本回传）。相应地 Task 4 的 asr.ts 需在内部维护 `finalText` 累计（每次 `sentence` 且 `final===true` 时 `finalText = text`），`completed` 时调用 `cbs.onCompleted(finalText)`；Task 4 测试的 completed 用例断言 `done` 即可（签名变化不影响既有断言，但 asr.ts 实现含累计逻辑）。

- 底部操作栏（:193-206）在"代表说/医生说"之前插入录音按钮：

```tsx
<TouchableOpacity
  style={[styles.simBtn, recording && { backgroundColor: Colors.danger }]}
  onPress={handleVoice}
  disabled={sending || transcribing}
>
  <Icon name={recording ? 'stop-circle' : 'microphone'} size={16} color={Colors.textWhite} />
  <Text style={styles.simBtnText}>{recording ? '停止录音' : '录音'}</Text>
</TouchableOpacity>
```

- 占位文案（:116-118）改为"点击底部按钮录音，实时转写对话内容"。
- 底部栏上方加转写中提示行（`transcribing || liveText` 时显示）：

```tsx
{(transcribing || liveText) && (
  <View style={{ paddingHorizontal: Spacing.md, paddingTop: Spacing.sm, backgroundColor: Colors.primarySurface }}>
    <Text style={{ fontSize: FontSize.xs, color: Colors.primary }}>
      {transcribing ? '转写中：' + (liveText || '...') : '点击停止录音'}
    </Text>
  </View>
)}
```

- [ ] **Step 3: ChatScreen 语音按钮接线（提示，非死按钮）**

`ChatScreen.tsx` :207-209 的 `voiceBtn` 加 `onPress`：

```tsx
const handleVoice = useCallback(() => {
  Alert.alert(
    '语音转写',
    '语音转写需在拜访流程中使用。\n（NLS 识别通道待配置后可用）',
    [{ text: '知道了' }]
  );
}, []);
```

```tsx
<TouchableOpacity style={styles.voiceBtn} onPress={handleVoice}>
```

- [ ] **Step 4: 测试 + 类型检查**

Run: `cd mobile && npx jest && npx tsc --noEmit`
Expected: 全部 PASS（asr 测试含新 completed 签名兼容）。

- [ ] **Step 5: Commit**

```bash
cd "/d/gongsi/medical system" && git add mobile/src && git commit -m "feat(mobile): 拜访页录音转写接线，ChatScreen 语音入口提示
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 批次 2 收尾 — 全量验证

- [ ] **Step 1: auth-service 全量 pytest**

Run: `cd services/auth-service && python -m pytest -q`
Expected: 全部通过（含新 test_sms.py 4 例）。

- [ ] **Step 2: mobile 全量测试 + 类型**

Run: `cd mobile && npx jest && npx tsc --noEmit`
Expected: 全部 PASS。

- [ ] **Step 3: 汇报**

汇总：短信 AliyunSmsSender 真实现与测试、录音依赖/权限、asr.ts 协议与单测、ChatScreen 语音入口（含 visitId 决策说明）、未真发短信/未真转写的原因（凭证缺失）。
