# MedAgent 真机联调指南（NLS / 百炼 key 配齐后）

> 目标：在真实 Android/iOS 设备上完成端到端验证 —— 录音实时转写、聊天 WS 流式、说话人分离、拜访全流程。
> 前置：本地后端可跑（见 CLAUDE.md Commands）；本指南假定已配齐阿里云密钥（百炼 + NLS + 短信）。
> 版本：2026-08-06（对应第四批修复后的代码状态）

---

## 1. 联调目标与前提

| 链路 | 现状（未配 key） | 配齐 key 后要验证 |
|------|-----------------|-------------------|
| 录音 → ASR WS | fail-closed（error 帧 + 关 4500，提示"NLS 识别通道未配置"） | 真机录音 → 实时出字 → 断句落库 → 每句合规检查回推 |
| 聊天 WS 流式 | 未端到端冒烟（8s 超时自动降级 REST） | 流式增量气泡 + 引用溯源 + 反馈/收藏 |
| 说话人分离 | 无真实 NLS 验证 | 转写区"代表/医生"标签正确区分 |
| 短信验证码 | console 打印（捞日志） | 阿里云短信真实下发 |

**前提清单**：
- [ ] 阿里云账号已开通：百炼（含多模态 App）、智能语音交互（NLS）、短信服务、OSS、DashVector（可选）
- [ ] 已有 AK/SK（`ALIYUN_ACCESS_KEY_ID`/`ALIYUN_ACCESS_KEY_SECRET`，建议使用 RAM 子账号最小权限）
- [ ] Android 真机（开启 USB 调试）或 iOS 真机（需 Mac + Xcode）
- [ ] 后端 8 服务本地可启动（postgres/redis 已跑、002 迁移已执行）

---

## 2. 环境准备

### 2.1 阿里云侧准备（一次性）

1. **百炼多模态 App**：控制台（bailian.console.aliyun.com）→ 创建多模态交互 App（如"肿瘤专员-小K"）→ 绑定知识库（上传说明书/文献，走审核）→ **发布应用**。发布后获得 App ID（`BAILIAN_APP_ID`，专员配置用）。
2. **百炼 API Key**：百炼控制台 → API-KEY 管理 → 创建（`BAILIAN_API_KEY`，与通义千问的 `DASHSCOPE_API_KEY` 是**两个不同 key**）。建议同时开通并记录 workspace/knowledge-base/index id（知识库同步用，可选）。
3. **NLS 智能语音交互**：控制台开通"实时语音识别"→ 创建项目 → 复制 Appkey（`NLS_APPKEY`）。**注意**：NLS 服务按量计费，联调时注意控制用量。
4. **短信服务**：签名（`AUTH_SMS_SIGN_NAME`，如"MedAgent"）+ 模板（`AUTH_SMS_TEMPLATE_CODE`，模板变量固定 `{"code": ...}`）。

### 2.2 `.env` 配置清单

| 变量 | 用途 | 联调取值 |
|------|------|---------|
| `ALIYUN_ACCESS_KEY_ID` / `ALIYUN_ACCESS_KEY_SECRET` | NLS token 换取 + 短信 | RAM 子账号 AK/SK |
| `NLS_APPKEY` | 实时语音识别 Appkey | NLS 控制台项目 Appkey |
| `NLS_SPEAKER_ENABLED` | 说话人分离开关（`1`/`true`/`yes`/`on`） | 先不配（默认关），验证 4.6 时开启 |
| `BAILIAN_API_KEY` | 百炼 WS 对话 | 百炼 API-KEY |
| `BAILIAN_APP_ID` | 数字专员=百炼 App（`digital_specialists.bailian_app_id`） | 每个专员一个 |
| `DASHSCOPE_API_KEY` | 合规语义规则 / 降级 qwen 直调 / AI 画像 | 通义千问 key |
| `AUTH_SMS_PROVIDER` | `console`（默认，捞日志）→ `aliyun`（真实下发） | 联调先 console，最后切 aliyun |
| `AUTH_SMS_SIGN_NAME` / `AUTH_SMS_TEMPLATE_CODE` | 短信签名/模板 | 短信服务控制台 |
| `AUTH_DEV_MODE` | `true` 时 `send-code` 响应回传验证码（**本地联调利器**） | 本地 `true`，生产必须 `false` |
| `NLS_WS_URL` / `NLS_TOKEN_URL` | NLS 网关地址（默认华东） | 默认即可，区域不同才改 |
| `INTERNAL_API_KEY` / `JWT_SECRET` | 内部鉴权 / JWT 签名 | `openssl rand -hex 32` 生成，**不得用模板值** |

> ⚠️ 改完 `.env` 后必须**重启**对应服务（env 启动时读取）。

### 2.3 后端启动

```bash
docker-compose up -d postgres redis
# 若首次：docker exec -i medagent-postgres psql -U medagent medagent < scripts/init_db.sql
# 若未执行过 002（审计不可篡改，audit 服务依赖 medagent_audit 角色）：
docker exec -i medagent-postgres psql -U medagent medagent \
  -v audit_password='<强密码>' < scripts/migrations/002_audit_immutable.sql
python scripts/seed_admin.py --phone 13812345678   # 设管理员密码 + 手机号（验证码登录用）

# 8 个服务各自直跑（见 CLAUDE.md Commands）：
cd services/auth-service && python -m uvicorn app.main:app --port 8007
cd services/gateway && python -m uvicorn app.main:app --port 8000
# ... specialist 8001 / visit 8002 / knowledge 8003 / compliance 8004 / audit 8005 / hcp 8006
```

**种子数据准备**（联调前必须）：
1. 建专员：`POST /api/v1/specialists`（admin token），`bailian_app_id` 填 2.1 步的百炼 App ID，status=`active`
2. 建医生：web 后台"医生管理"或 `POST /api/v1/hcps`
3. 传文档：web 知识库页上传 + 审核通过（或调 review 端点）

### 2.4 移动端准备（真机）

**⚠️ 关键：真机无法访问 `10.0.2.2`（那是模拟器专用地址）**，需把三个 host 常量改为宿主机局域网 IP（如 `192.168.1.100`）：

| 文件 | 当前（模拟器） | 改法 |
|------|--------------|------|
| `mobile/src/api/client.ts:11-13` | `android: 'http://10.0.2.2:8000'` | `'http://<宿主机IP>:8000'` |
| `mobile/src/services/asr.ts:11-13` | `android: '10.0.2.2:8002'`（**直连 visit-service，不走网关**） | `'<宿主机IP>:8002'` |
| `mobile/src/services/wsChat.ts:8-10` | `android: '10.0.2.2:8000'` | `'<宿主机IP>:8000'` |

> iOS 真机无此项（localhost 即真机自身）——iOS 需走 `localhost:8000`，真机场景要改为电脑 IP + **HTTPS 或 ATS 例外**（另见 5.3）。

**宿主机防火墙放行 8000-8007 端口**（Windows：控制面板 → 防火墙 → 入站规则放行；或 `netsh advfirewall firewall add rule ...`）。

```bash
# 构建安装（Android）
cd mobile/android && ./gradlew assembleDebug
adb devices                          # 确认真机已连接（USB 调试开启）
adb install -r mobile/android/app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.medagent.mobile/.MainActivity
# 抓日志（联调排障利器）
adb logcat -s ReactNativeJS:V
```

---

## 3. 后端冒烟验证（先于真机，快速定位后端问题）

```bash
# 1. 健康检查（8 个服务都 200）
curl -s localhost:8000/health        # 网关（现在会真探活各服务，看 services 字段）
curl -s localhost:8001/health

# 2. 登录（AUTH_DEV_MODE=true 时验证码直接回传）
curl -s -X POST localhost:8000/api/v1/auth/send-code -H 'Content-Type: application/json' \
  -d '{"phone":"13812345678"}'
curl -s -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"phone":"13812345678","code":"<响应里的code>"}'
# → 拿 token，存 T="Bearer <token>"

# 3. 专员列表（应看到 active 专员，分页形状 {items,total,...}）
curl -s localhost:8000/api/v1/specialists -H "Authorization: $T"

# 4. 专员对话 REST（真百炼 key：应返回 citations/evidence_level；无 key：降级 qwen）
curl -s -X POST localhost:8000/api/v1/specialists/1/chat -H "Authorization: $T" \
  -H 'Content-Type: application/json' -d '{"question":"这个药的用法用量？"}'

# 5. 合规预检（内部接口，需 X-Internal-Key——先在 shell 里 export IK="<INTERNAL_API_KEY>"）
curl -s -X POST localhost:8000/api/v1/compliance/check -H "X-Internal-Key: $IK" \
  -H 'Content-Type: application/json' \
  -d '{"content":"保证治好","context":{"type":"manual_test"}}'
# → 预期 blocked=true，violations 含 R001

# 6. 语义合规（DASHSCOPE_API_KEY 配齐后）——问"帮我查下张医生上个月开了多少盒"
#    → blocked=true（R003 统方）；若 key 未配，语义规则跳过（仅关键词/正则生效）

# 7. 审计查询（角色限制：admin/manager/compliance 才能看）
curl -s "localhost:8000/api/v1/audit/logs?page_size=3" -H "Authorization: $T"
#    → 应有 chat_response 等记录；request_id 非空（X-Request-ID 已贯穿）
```

---

## 4. 真机端到端验证（核心清单）

### 4.1 登录
| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 打开 App → 验证码登录 → 输手机号 → 获取验证码 | 60s 倒计时；console 模式下验证码在 `logs/native/auth-service.log`（grep `验证码`）；aliyun 模式收到真实短信 |
| 2 | 输码登录 | 进入工作台；退出再进（杀进程）不掉登录态 |
| 3 | 切"密码登录" | 用户名+密码可登录（管理员需先 seed_admin 设密码） |
| 4 | 网络断开时冷启动 | **不掉登录态**（仅 401 才登出） |

### 4.2 专员对话（WS 流式 + 降级）
| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 对话 Tab → 专员列表 → 进入对话 | 专员卡片状态正常（active 可点） |
| 2 | 提问"剂量怎么调" | **3s 内** start 帧 → 增量气泡逐字渲染 → done 帧带 conversation_id |
| 3 | 追问（多轮） | 上下文连续（dialog_id 续传） |
| 4 | 看答案底部 | 引用来源卡片 + 证据等级（百炼正文无【证据等级】标记则恒 None——已知限制） |
| 5 | 点赞/收藏 | 返回成功；重进页面收藏仍在 |
| 6 | 断网（飞行模式）后发送 | **8s 内无 start → 自动降级 REST**，有错误提示 |
| 7 | 局域网内关掉 specialist-service | 降级到 qwen 直调（citations 空，符合预期） |

> ⚠️ 观察点：流式答案的**合规审核在全文推送后执行**（已知技术债）——故意问违规内容（如"这药保证治好"）时，违规文本会先展示、done 帧才给掩码文案。联调时记录该行为是否可接受。

### 4.3 拜访全流程（核心场景）
| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 工作台 → 今日拜访（或添加）→ 拜访前准备 | 医生画像/推荐话题/红线/开场白/上次跟进真实显示（pre-visit 已 schema 化） |
| 2 | 开始拜访 | 进入拜访中页，`visit_id` 正常（不再 undefined） |
| 3 | **点录音 → 说话 30s** | 实时出字（增量回填）；说话人标签（配 NLS_SPEAKER_ENABLED 后） |
| 4 | 说一句违规话（如"这药保证有效"） | 红线弹窗/警告出现（compliance 帧已接线） |
| 5 | 说"这个药多少钱"或"副作用" | 异议识别提示出现 |
| 6 | 结束拜访 | 拜访后页显示**真实 AI 摘要**（非假数据）；关键点/兴趣/异议/情感/下次计划 |
| 7 | 确认完成 + 分享 | 成功提示；分享面板带摘要文本 |
| 8 | 回工作台 | 拜访卡片状态"已完成"、时长正常；**任务列表出现自动创建的后续任务**（end_visit 自动建） |
| 9 | 医生详情 → 互动历史 | 本次拜访记录在列（visit_time/ai_summary 真实渲染） |

**录音链路注意**：
- 当前实现是"录完再推"（audio-record 无流式回调，停止后一次性突发推 16KB×N 分片 + 立即 stop）——**与 NLS 实时流式要求存在设计级不匹配**，长音频（>1 分钟）可能丢帧/拒收。联调时：先试 30s 内短音频；若长音频转写不全，记录现象（这是已知待修点，不是配置问题）。
- 录音权限弹窗必须允许（Android 13+ 麦克风权限）。

### 4.4 说话人分离（4.6 节单独验证）
`.env` 设 `NLS_SPEAKER_ENABLED=1` → 重启 visit-service → 重新拜访录音 → 观察转写区是否出现"代表/医生"标签。**注意**：参数名 `enable_speaker_identity`/`speaker_diarization` 是按阿里云文档写的，**真机验证时若报错或无效，需按实际返回调整 `realtime_asr.py` 的 `_build_start_payload()`**（代码注释已标注待确认点）。

### 4.5 其余页面抽查
- 内容页：分类 Tab 有数据（知识库有 ready 文档时；空库时"全部"为空属正常）
- 合规手册：红线清单来自真实规则（reject 类）；失败显示错误态
- 我的：统计概览真实（拜访总数不再显示 undefined）；设置页各入口有响应
- 帮助中心：红线清单真实数据

---

## 5. 已知待确认点（联调时重点观察并记录）

| # | 待确认项 | 位置 | 联调动作 |
|---|---------|------|---------|
| 1 | NLS 说话人分离参数名/取值（`enable_speaker_identity`/`speaker_diarization`） | `visit-service/app/services/realtime_asr.py` `_build_start_payload()` | 开 NLS_SPEAKER_ENABLED 实测；报错则按 NLS 实际文档修正 |
| 2 | NLS speaker_id → rep/doctor 对应约定（现按 0=代表/1=医生） | `visit-service/app/api/asr_ws.py` `_map_speaker()` | 两人对话实测标签是否正确，不对就调映射 |
| 3 | "录完突发推流"长音频丢帧 | `mobile/src/services/asr.ts` | 30s/60s/3min 音频各测一次，记录转写完整度 |
| 4 | 百炼流式 60 帧上限（超长回答第 61 帧断） | `specialist-service/app/services/bailian_client.py:162-191` | 问一个超长问题观察是否中断 |
| 5 | iOS 首次构建（本机无 Xcode，未验证过） | mobile/ios | Mac 上 `pod install` + Xcode 构建；moduleName 已对齐但未实测 |
| 6 | iOS 真机访问后端需 HTTPS/ATS 例外 | mobile/ios Info.plist | 或改用局域网 IP + ATS 白名单 |
| 7 | 百炼 App 侧 prompt 是否输出【证据等级】标记 | 百炼控制台 | 不输出则 `evidence_level` 恒 None（已知限制） |

---

## 6. 排障手册

### 6.1 日志位置

| 场景 | 位置 |
|------|------|
| 验证码（console 短信） | `logs/native/auth-service.log`（grep 验证码/code） |
| 各服务启动/报错 | `logs/native/<service>-service.log` |
| 移动端 JS 错误 | `adb logcat -s ReactNativeJS:V` |
| 合规拦截 | `compliance_blocks` 表（web 拦截记录页可查） |
| 审计留痕 | web 审计查询页（含 request_id） |
| 百炼/NLS 调用 | 各服务日志（`logger.warning` 级别可见降级） |

### 6.2 常见问题

| 现象 | 原因/处理 |
|------|----------|
| 录音提示"NLS 识别通道未配置" | NLS_APPKEY 未配或服务未重启（fail-closed 是**预期行为**，配齐后消失） |
| 聊天一直转圈 8s 后变一次性回答 | 百炼 key 未配/专员 bailian_app_id 未填/专员非 active → 自动降级 REST（预期） |
| 专员列表空 | 后端无 active 专员 → web 建专员 |
| 登录 401 / 403 | token 过期（7 天）；角色不符（如 rep 访问审计页）→ 用 admin 账号 |
| WS 关 4500 | question 空/超时/异常——看服务端日志具体原因 |
| 验证码收不到短信 | 先确认 console 模式捞日志；切 aliyun 需配齐签名+模板，缺配**启动即抛错**（fail-fast） |
| 真机连不上后端 | ① host 改局域网 IP（不是 10.0.2.2）② 防火墙放行 8000-8007 ③ 手机与电脑同一 WiFi |
| ASR 能连但一直不出字 | 麦克风权限未给；或长音频突发推流丢帧（见 5.3） |
| 审计页看不到数据 | 角色非 admin/manager/compliance（已加角色限制）；或 AUDIT_DATABASE_URL 未配（002 后写入静默失败——启动前必查） |
| 知识库检索空 | 文档未 ready（需审核通过）；knowledge-base 无内容（当前空库属预期） |

### 6.3 快速回滚点
- 说话人分离异常 → 去掉 `NLS_SPEAKER_ENABLED` 重启 visit-service 即回退（帧缺省 rep，移动端无标签，向后兼容）
- 短信异常 → `AUTH_SMS_PROVIDER` 切回 `console` 重启 auth-service

---

## 7. 验收清单（全过即真机联调完成）

- [ ] 验证码短信真实下发（或 console 捞码）→ 登录成功、冷启动不掉登录态
- [ ] 密码登录可用
- [ ] 专员对话 WS 流式：3s 内出字、多轮连续、引用/证据等级展示、反馈收藏落库、8s 降级 REST 生效
- [ ] 录音转写：30s 音频实时出字、断句落库、违规话术弹红线、异议提示出现
- [ ] 说话人分离（开 NLS_SPEAKER_ENABLED）：标签正确（或记录参数修正点）
- [ ] 拜访全流程：准备包 → 拜访中 → 结束生成真实摘要 → 确认完成/分享 → 工作台状态 → 自动任务
- [ ] 医生详情：画像真实、互动历史含本次拜访
- [ ] 审计页：记录含 request_id（X-Request-ID 贯穿）、时间无 8 小时偏移
- [ ] web 端：仪表盘热力图/实时动态有数据、拦截记录页可查、系统配置页显示已配置状态
- [ ] 记录第 5 节 7 个待确认点的实测结果（特别是说话人分离参数与长音频转写完整度）

**联调产出**：把第 5 节待确认点的实测结果更新回本指南 + 修 `realtime_asr.py`/`asr.ts` 相关代码，并把结论同步到 CLAUDE.md。
