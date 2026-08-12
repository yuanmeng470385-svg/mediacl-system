# 设计：web 医生管理补全 + 移动端语音链路补全（2026-08-11）

## 1. 背景与目标

MedAgent 已修过 60 项审计发现，剩余未修缺口中的一批本轮处理：

1. **web 医生管理**：`DoctorList`「新增医生」按钮仅 `message.info` 占位；AI 画像接口 `GET /hcps/{id}/profile` 已定义但无页面调用
2. **移动端语音输入**：真实链路（录音→PCM→WS→NLS）已接，仅差 `.env` 的 `NLS_APPKEY` 配置；另有设计缺口 **M19**（"录完突发推流"与 NLS 流式识别不匹配）
3. **TTS 未接**：需求仅技术选型一句话（听悟承担 ASR/TTS），无产品级定义
4. **关键节点标记/话术建议实时推荐**：需求标注"后续版本"，目前完全空白
5. **真机端到端未跑**：mobile 三处 host 写死，无流式验证

另外用户确认：百炼 App 已发布，对话恒降级 qwen 问题已解决（本轮仅文档更新）。

**目标**：新增医生 + AI 画像展示上线；语音输入完整接线（流式 + MOCK 联调验证）；TTS 朗读话术建议；LLM 实时推荐关键节点与话术；host 集中可配置 + runbook 更新。

## 2. 范围

### 做
| # | 模块 | 内容 |
|---|------|------|
| 1 | web | DoctorList 新增医生 ModalForm（真实接线 `POST /hcps`） |
| 2 | web | DoctorDetail AI 画像卡片（调用 `GET /hcps/{id}/profile`，含降级兼容） |
| 3 | visit-service | `GET /api/v1/nls/tts-token` 端点（复用 NLS token 换发） |
| 4 | visit-service | sendTranscript 链路 LLM 实时推荐（关键节点 + 话术建议，节流 + 降级） |
| 5 | DB | 迁移 006：`visit_records.key_nodes` JSONB 列 |
| 6 | mobile | 语音流式推流（M19 修复：轮询增量读 WAV → WS） |
| 7 | mobile | `tts.ts` 服务 + 拜访中「话术建议朗读」按钮（react-native-sound） |
| 8 | mobile | 拜访中「AI 实时推荐」区（关键节点徽标 + 建议卡片） |
| 9 | mobile | `config.ts` 集中三处 host，真机单点修改 |
| 10 | mobile | ChatScreen 麦克风按钮文案更新 |
| 11 | 测试 | visit-service 单测（tts-token 409 / LLM 节流降级 / 迁移）；mobile jest；web build |
| 12 | 文档 | CLAUDE.md 状态更新（已修划掉 + 新端点/迁移/配置）；`real-device-runbook.md` 更新 |

### 不做（YAGNI，后端已就绪）
- web 医生编辑 / 删除 / 批量导入 UI（`PUT /hcps`、`batch-import` 后端已有）
- 聊天页录音转写（ASR WS 绑定真实 visit_id，需新端点，超范围）
- 关键节点手动标记（需求"自动加手动"，本轮只做 AI 自动）
- TTS 服务端代理端点（用户已选定移动端直调 NLS）
- 说话人分离真机调参（`enable_speaker_identity` 参数名待真机确认，本轮不改）

## 3. 架构总览

```
web (React + antd Pro)
  DoctorList ──POST /api/v1/hcps──▶ gateway:8000 ──▶ hcp-service:8006（已就绪）
  DoctorDetail ──GET /hcps/{id}/profile──▶ 同上（已就绪）

mobile (RN)
  config.ts（host 集中）
  asr.ts ──WS /ws/visits/{id}/asr──▶ visit-service:8002（直连，网关不代理 ASR WS）
  tts.ts ──GET /api/v1/nls/tts-token──▶ gateway ──▶ visit-service:8002
         ──NLS REST 合成（wss/nls-gateway）──▶ 播放（react-native-sound）
  VisitInProgressScreen ──POST /visits/{id}/transcript──▶ gateway ──▶ visit-service
                            └──响应含 key_nodes + ai_suggestion（LLM 推荐）
```

关键通道约束（现状保持）：
- ASR WS **不走网关**（网关 proxy 不支持升级），直连 8002
- 新 `tts-token` 端点走网关（`ROUTE_MAP` 加 `/api/v1/nls` → visit-service）
- transcript 仍走 REST（现链路），LLM 推荐随响应返回，不新增 WS 通道

## 4. 模块设计

### 4.1 Web 医生管理（纯前端，后端零改动）

**新增医生**（`web/src/pages/Doctor/DoctorList.tsx`）：
- 参考 `web/src/pages/User/UserList.tsx` 的 ModalForm 模式：`formOpen` + `editing` 状态、`ModalForm` + `ProFormText/ProFormSelect`、`initialValues`、`onFinish` 后 `actionRef.reload()`
- 表单字段与后端白名单 `HCP_WRITABLE_FIELDS`（hcp_repo.py:13-17）严格对齐：`name`（必填）/ hospital / department / title / specialty / phone / email / region / influence_level（high|medium|low select）/ tags（多选或逗号）/ status（默认 active，不展示或默认值）
- 提交 `doctorAPI.create`；400 时表单保留（`onFinish` 返回 false）
- 非 admin/manager 用户隐藏按钮（`useAuth().user.role`，同 UserList.tsx:21）
- 字段类型：`Doctor` 类型（`web/src/types/index.ts:189-199`）扩展 `specialty/email/region/influence_level/status`

**AI 画像**（`web/src/pages/Doctor/DoctorDetail.tsx`）：
- 新增 `ProfileResponse` TS 类型（`doctor.ts`），后端结构（hcps.py:116-119）：
  ```ts
  interface ProfileResponse {
    ai_profile: {
      academic_profile: string; prescription_preference: string;
      communication_advice: string; next_step_suggestion: string;
      risk_alert: string;
    } | { summary: string; base_info: Record<string, string> }; // degraded 形状
    interactions: Interaction[]; degraded: boolean; hcp: Doctor;
  }
  ```
- 页面加载 `Promise.all([detail, interactions, profile])`；新增「AI 画像」Card（Descriptions 布局）：5 字段逐行展示；`degraded === true` 时展示 `summary` + `base_info` 降级提示
- **映射逻辑直接移植移动端** `mobile/src/api/hcp.ts:81-154`（`mapProfile`/`mapCommunication`/`mapRiskAlert`，降级判定 `base_info in ai_profile` 或 null）：web `doctor.ts` 补 `RawHCPProfile` + `mapProfile` 和 `HCPProfile` 类型（现为 `any`），字段规则（risk_alert 解析、communication 对象抽取、prescription 拆分）与移动端一致，避免两端契约漂移
- 画像调用触发 qwen-max（付费 + 审计），页面加载即调；不做手动触发按钮（Detail 页信息密度低，自动加载合理）

### 4.2 visit-service：TTS token 端点

新端点 `services/visit-service/app/api/tts.py`（或并入现有 api 模块）：
- `GET /api/v1/nls/tts-token`，`require_roles("rep", "admin", "manager")`（任意登录 active 用户）
- 逻辑：检查 `NLS_APPKEY`；未配 → 409 业务错误（code 4xxx，message "NLS 未配置"）；已配 → 复用 `realtime_asr.py` 的 `get_nls_token`（AK/SK HMAC-SHA1 签名，24h 进程内缓存），返回 `{token, appkey, expires_at}`
- token 换发逻辑从 `RealtimeAsrClient` 抽出为模块级函数 `get_nls_token()`（现有实现不动，仅提为可复用），避免重复签名代码
- 网关 `main.py` ROUTE_MAP 加 `"/api/v1/nls": settings.VISIT_SERVICE_URL`

**安全**：token 是短期凭证（NLS token 有效期 24h），经网关 JWT 校验后下发合理；appkey 非机密（项目标识），放移动端无风险。AK/SK 永不出服务端。

### 4.3 visit-service：LLM 实时推荐（关键节点 + 话术建议）

扩展 `sendTranscript` 链路（`visit_manager.py` 的 transcript 处理处）：
- **触发条件**（节流）：同 visit 冷却 20s；新增句 `len(strip()) >= 6` 且非纯标点；异步执行（`asyncio.to_thread`）
- **LLM 调用**：qwen-turbo（快、便宜），prompt 要求严格 JSON 输出：
  ```json
  {
    "key_nodes": [{"type": "decision_point|interest_point", "label": "短标签", "quote": "引用原句"}],
    "suggestion": {"topic": "异议主题", "advice": "应对话术建议"}  // 无可建议时 null
  }
  ```
- **超时与降级**：总超时 8s；LLM 异常/超时/解析失败 → 不阻塞 transcript 主流程（try/except + 审计日志），响应中 `ai_recommendation: null` 或上次结果
- **落库**：key_nodes 追加写入 `visit_records.key_nodes`（JSONB 数组），`GET /api/v1/visits/{id}` detail 返回
- **响应**：transcript 响应合并返回 `{..., key_nodes, ai_suggestion}`；现有规则版 `objection_responses` 保留，两者并存（规则版即时、LLM 版增强）
- 节流窗口内新句只返回规则版结果（`key_nodes/ai_suggestion` 为 null 或上次值，前端幂等处理）

### 4.4 迁移 006

`scripts/migrations/006_add_visit_key_nodes.sql`（对照 005 格式）：
```sql
ALTER TABLE visit_records ADD COLUMN IF NOT EXISTS key_nodes JSONB;
```
模型 `shared/models/visit_record.py`（或 visit-service 侧）加 `key_nodes = Column(JSONB, nullable=True)`。to_dict 时输出。

### 4.5 mobile：语音流式推流（M19 修复）

`mobile/src/services/asr.ts` 增加流式推流模式（保留现有 `pushAllAndStop` 供降级）：
- 新增 `connectAsrStreaming(visitId, token, cbs, {pollMs = 2000})`：`onReady` 后启动轮询——recorder.ts 的 `readWavPcm` 扩展为 `readWavPcmFrom(path, offset)`：用 **RNFS.readFile(path, 'base64', position, length)**（react-native-fs 原生支持字节级 position/length，recorder.ts:5 已用该库，无新依赖）从指定偏移读增量 PCM（跳过 44 字节头），每次读新增长度按 16KB 分片推 WS
- `stop()`：停止轮询 → 推剩余 PCM → `{"type":"stop"}`
- 服务端 `asr_ws.py` 零改动（已支持持续二进制 feed + 收尾 stop）
- 轮询读取与录音写入同文件并发：Android 下 audio-record 写 WAV 头后持续追加 PCM，按字节偏移读尾部可行；文件长度用 RNFS.stat（recorder.ts 已依赖 react-native-fs，无新依赖）
- **验证限制**：Android 模拟器无麦克风，流式路径需真机；联调用 `NLS_MOCK=1`（Mock 每段喂入吐固定句，可验证推流节奏）

**联调配置**：`.env` 加 `NLS_APPKEY=`（占位，用户填真实值）+ `NLS_MOCK=1`（开发联调；Mock 文本不落库，asr_ws.py:130-133 现有语义）。

### 4.6 mobile：TTS 朗读

新 `mobile/src/services/tts.ts`：
- `getTtsToken()`：GET `/api/v1/nls/tts-token`（走 client.ts，JWT 自动带）
- `synthesize(text)`：调 NLS REST 合成
  `https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts?appkey={appkey}&token={token}&text={encodeURIComponent(text)}&format=wav&sample_rate=16000`
  → 返回音频字节 → 写临时 wav 文件 → `react-native-sound` 播放（`new Sound(path)`，play on load 完成）
- 状态管理：单例播放（正在播时新请求忽略或打断重播）；`cleanup()` 释放
- 未配 NLS（tts-token 409）→ 朗读按钮禁用 + 提示"语音合成未配置"
- **新依赖**：`react-native-sound`（需老板拍板——mobile 端首个音频播放库；替代品 expo-av 更重，原生工程下选 react-native-sound）

UI（`VisitInProgressScreen.tsx`）：ObjectionAlert 话术建议卡片加「🔊 朗读」按钮 → `tts.synthesize(suggested_response)`。

### 4.7 mobile：AI 实时推荐区

`VisitInProgressScreen.tsx` 新增「AI 实时推荐」区块（在异议卡片区下方）：
- 关键节点：横排徽标（decision_point → 蓝色"决策点"、interest_point → 绿色"兴趣点"）+ label + quote（截断）
- AI 话术建议：卡片（topic 标题 + advice 文案 + 「朗读」按钮，复用 4.6 的 TTS）
- 数据流：`mapTranscriptResult`（`mobile/src/api/visit.ts:184-200`）扩展解析 `key_nodes` / `ai_suggestion` → 组件状态累积渲染
- ChatScreen 麦克风按钮（ChatScreen.tsx:215-222）：文案改为「语音转写需在拜访流程中使用」（去掉"NLS 待配置"字样，因链路已完整）

### 4.8 mobile：host 集中可配置

新 `mobile/src/config.ts`：
```ts
import { Platform } from 'react-native';
const DEV_HOST = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
export const API_HOST = DEV_HOST;      // 真机改为局域网 IP（如 192.168.x.x）
export const ASR_HOST = DEV_HOST;
export const GATEWAY_HOST = DEV_HOST;
```
`client.ts` / `asr.ts` / `wsChat.ts` 改读 config.ts（行为不变，单点修改）。

### 4.9 测试

| 层 | 用例 |
|---|---|
| visit-service | tts-token：已配返回 token 结构 / 未配 409；LLM 推荐：节流窗口内不触发（mock LLM 计数）、LLM 异常不阻塞 transcript（返回 null 降级）、key_nodes 落库（mock DB 断言 JSONB 追加）、结构化解析成功路径 |
| mobile jest | config.ts 导出；tts.ts 的 token 获取/合成 URL 构造（mock fetch）；asr streaming 分片逻辑（mock 文件读取）；mapTranscriptResult 新字段解析 |
| web | `npm run build` 通过；手工验证新增表单 + 画像卡片 |

### 4.10 文档更新

- **CLAUDE.md**：
  - 百炼 App 已发布 → 从「未修」划掉（对话降级解决，用户确认）
  - 本轮修掉的划掉：web 医生管理缺口（新增医生 + AI 画像）、移动端语音 stub（改为"已接流式"）、听悟 TTS 未接、NLS_APPKEY 未配（改"已配 MOCK 联调"）、关键节点标记/话术建议实时推荐（后续版本 → 已做 LLM 版）
  - 新增记录：`GET /api/v1/nls/tts-token`、迁移 006、`visit_records.key_nodes`、mobile `config.ts` 集中 host、react-native-sound 依赖（如需拍板则记录）、NLS 合成 REST 用法
  - 真机项保留：流式推流/说话人分离/端到端待真机（runbook 指引）
- **real-device-runbook.md**：NLS_APPKEY 配置、NLS_MOCK 联调、config.ts 改 host、TTS 验证步骤

## 5. 错误处理汇总

| 场景 | 行为 |
|---|---|
| tts-token 未配 NLS_APPKEY | 409 + 明确 message；mobile 按钮禁用提示 |
| NLS token 换发失败（AK/SK 无效） | 5003 第三方错误；mobile 提示后重试 |
| LLM 推荐超时/异常 | 静默降级（日志 + 审计），transcript 主流程不受影响 |
| TTS 合成失败 | 按钮无响应 + Alert 提示，不影响其余 |
| 播放中断（用户再点） | 打断旧播放重播 |

## 6. 风险与开放点

1. **react-native-sound 新依赖**：需老板拍板（mobile 端首个播放库）；若被否，降级方案为 expo-av 或暂缓朗读按钮
2. **边录边推轮询方案**：同文件读写并发依赖 audio-record 的 WAV 追加写行为，模拟器无麦克风无法本地验证，需真机确认
3. **LLM 实时推荐成本**：qwen-turbo + 20s 冷却，单次拜访（~20 句）约触发 3-5 次调用，成本可接受；若超预算可将冷却提到 60s
4. **NLS REST 合成参数**：voice/format 用默认（Xiaoyun 或默认音色），后续可配
