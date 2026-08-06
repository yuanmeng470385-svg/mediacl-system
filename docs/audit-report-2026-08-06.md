# MedAgent 全仓代码审计报告

> 审计日期：2026-08-06　|　审计方式：11 个并行审计代理逐文件审查 + 关键结论人工复核
> 范围：services/（8 服务 + 网关）、shared/、scripts/、tests/、deploy/、web/、mobile/ 全部源码（约 2 万行）
> 依据：AI数字员工系统-完整方案.md（v4.0）+ CLAUDE.md

---

## 1. 总览

| 级别 | 数量 | 说明 |
|------|------|------|
| Critical | 21 | 功能直接不可用 / 安全直接受损 |
| Major | 48 | 功能部分失效 / 显著缺陷 |
| Minor | 60+ | 加固项 / 契约脆弱点 |

**结构性结论：全项目最深的问题是"前后端契约大面积脱节"** —— 分页形状、字段名、筛选参数名、响应键名在 web/mobile 与后端之间几乎全面不一致。服务端单测全绿（22+19 个），但真实链路在 UI 层大量断裂，且断裂点集中在 `web/src/pages/*` 与 `mobile/src/api/*.ts` 的映射层。

---

## 2. Critical 问题（按影响排序）

### 2.1 移动端拜访全流程断裂（4 个连锁 bug）

| # | 问题 | 证据 |
|---|------|------|
| C1 | `startVisit` 期望 `{visit_id}`，后端 `start_visit` 返回 `record.to_dict()`（只有 `id`）→ `visitId=undefined` → 后续 transcript/ASR WS/end 全部请求 `/visits/undefined/...` | `mobile/src/api/visit.ts:32-38` vs `services/visit-service/app/core/visit_manager.py:266`（**已复核**） |
| C2 | `endVisit` 被调用两次（VisitInProgressScreen + VisitEndScreen），第二次触发后端"已结束"锁 → 必然抛错 → 落入**写死的假摘要**（"本次拜访就产品最新临床数据…"），用户必看伪造数据 | `VisitInProgressScreen.tsx:86` + `VisitEndScreen.tsx:43-58` + `visit_manager.py:363-366` |
| C3 | `process_transcript` 响应键错位：移动端读 `objections[]/compliance_alerts`，后端返回 `objections:{...}/compliance` → 拜访中**异议提示与合规红线提醒永不显示**（整段死代码） | `mobile/src/api/visit.ts:41-57` vs `visit_manager.py:300-330` |
| C4 | `endVisit` 失败后展示写死的假摘要 + 假跟进计划（注释明写 "// Mock 展示"），且因 C2 正常流程必走该路径 | `VisitEndScreen.tsx:45-58,68-75` |

**建议修复点**：全部集中在 `mobile/src/api/visit.ts` 映射层 + VisitEndScreen 去掉 Mock 兜底 + 去掉重复 end 调用。

### 2.2 分页契约全局错位

- 后端 `paginate()` 返回 `{items, pagination:{total,...}}`，前端约定/读取 `{items,total,page,page_size}` → **web 6 个列表页 total 恒 undefined**（分页/总条数全失效）、Dashboard 用户数/对话量恒 0、mobile 我的页显示字符串 "undefined"。证据：`shared/common/pagination.py:34-41`（**已复核**）+ `web/src/types/index.ts:2-11`。前端 6 处解包点、Dashboard 2 处同源。

### 2.3 互动历史契约错位 → 两个必崩页面

- 后端互动历史包 `{items:[...]}`，web 与 mobile 均按裸数组解包 → **web 医生详情页打开必白屏崩溃**（`web/src/pages/Doctor/DoctorDetail.tsx:18,45`）、**mobile 互动历史 Tab 必崩**（`HCPDetailScreen.tsx:282`）。证据：`services/hcp-service/app/api/hcps.py:96-105`。
- 同源：mobile 画像 Tab 读 `basic_info/academic_profile.background/prescription_analysis`，后端返回 `{name,hospital,...}/academic_profile(字符串)` → 画像 Tab 全空白（`profile_generator.py:24-30,66` vs `HCPDetailScreen.tsx:184-271`）；web 详情页读 `doctor.education/preferences`，后端是 `academic_background/prescription_preference` → 恒"暂无"。

### 2.4 安全类

| # | 问题 | 证据 |
|---|------|------|
| C5 | **specialist 会话历史 IDOR**：`GET /conversations/{session_id}` 无 user_id 归属校验，任意登录用户持他人 session_id 可读全量对话历史；REST/WS chat 同样接受任意 session_id 续传他人会话 | `specialists.py:143-154` + `chat_ws.py:81` |
| C6 | **compliance LLM 异常形状 fail-open 绕过 R999**：LLM 返回 `content=None`/空 choices/JSON 形状错误时抛 AttributeError/IndexError，不在 fail-closed 的 except 元组内 → 落入 `except Exception → return []` 放行。恰是"注入/截断迹象"应拦截的场景（已实测复现） | `checker.py:283-298`（**已复核**） |
| C7 | **auth audit_client 签名缺 `before_value`**：`PUT /users/{id}` 在 db.commit() 之后抛 TypeError → 用户更新已落库但前端报 500，且 `user_update` 审计永不写入 | `auth-service/app/services/audit_client.py:16-25`（**已复核**）+ `users.py:119-124` |
| C8 | **INTERNAL_API_KEY 弱密钥可被模板绕过**：`.env.example` 的占位值 ≠ 代码 DEFAULT → 照抄模板部署时守卫不触发，系统带公开可猜的 key 启动，可伪造 X-Internal-Key 调 `/compliance/check`（触发付费 LLM）/`/audit/log`（伪造审计） | `shared/common/internal_auth.py:21,31` + `.env.example:50` |
| C9 | **manager 可自授 admin**：`require_roles("admin","manager")` 的 PUT /users 白名单含 `role`，无"仅 admin 可改角色/禁自授"约束 | `auth-service/app/api/users.py:99-125` |
| C10 | **RBAC 只信 token 声明**：除 profile/me 外所有端点不重读库、不查 status → 被停用的 admin 持 7 天 JWT 仍可建号/改角色；角色降级 token 过期前不生效 | `shared/common/auth.py:59-93` |
| C11 | **验证码 off-by-one + 账号枚举**：第 5 次（上限次）校验必败（先 +1 再判 `>=`）；exhausted 报错文案与通用错误不同 → 攻击者 5 次探测即可确认手机号是否注册 + 反复作废他人验证码（DoS） | `auth.py:192-195` + `code_store.py:94-97`（已实证） |
| C12 | **听悟归档转写必然失败**：GetTaskInfo 的 Result 是带签名 URL 的字典/JSON 字符串，`_parse_result` 直接 `.get("transcripts")` → dict 取 None、str 抛 AttributeError | `tingwu_client.py:83-96` |

### 2.5 Web 端假动作/必败（CLAUDE.md 已知问题验证后全部属实且无收敛）

| # | 问题 | 证据 |
|---|------|------|
| C13 | 专员列表恒空：后端返回裸数组且只 `active`，web 按 `{items,total}` 解包；创建/编辑/停用全是 toast 假动作；StatCard 硬编码 12/10/1342 | `SpecialistList.tsx:55-79` + `specialists.py:24-27` |
| C14 | 合规规则页全面失效：字段名错（code/name/pattern vs rule_code/rule_name/content）→ 列表空、**新增必 400**、编辑"成功"但无字段更新 | `ComplianceList.tsx:27-33,70-76` |
| C15 | 审计页：筛选参数全错（start_date/service/operation vs start_time/service_name/action）→ **高级搜索全失效**；统计写死 15,832/423；展开行写死假数据；导出 blob 被丢弃（用户拿不到文件，且无 body 必 422） | `AuditList.tsx:31-60` |
| C16 | 用户新增必败（表单无 username 字段）；编辑 name 不在白名单（后端要 full_name）→ 静默"成功"；ModalForm 无 destroyOnHidden → 编辑 A 后编辑 B 会**把 A 的数据写入 B**（数据损坏） | `UserList.tsx:50-63` |
| C17 | 知识库列表页 `r.type.toUpperCase()` 必抛 TypeError（后端是 `doc_type`，web 是 `type` 且取值语义错）→ 页面不可用；上传是假动作（Dragger 无请求）；审核按钮依赖不存在的 `pending` 状态 → **医学顾问无法在 web 审核**；stats 字段错恒 0 | `KnowledgeList.tsx:22,33,65-71` |
| C18 | 系统配置页全假动作（保存只弹 toast，无加载/无接口） | `SystemConfig.tsx:10` |
| C19 | `/api/v1/knowledge/search` 网关两侧双向不可达：网关按 INTERNAL_PATHS（要 X-Internal-Key 免 JWT），服务端却挂 `get_current_user`（要 JWT）且无 `require_internal_key` → web 调 403、内部调 401 | `gateway/app/core/auth_middleware.py:45` + `knowledge.py:48-51`（**已复核**） |

### 2.6 部署配置

| # | 问题 | 证据 |
|---|------|------|
| C20 | **生产 compose 审计写入 100% 静默失败**：prod audit-service 无 `AUDIT_DATABASE_URL` 覆盖（.env.example 也没有）→ 用 medagent 账号连库，002 迁移后该账号对 audit_logs 仅 SELECT → 所有审计写入静默失败（logger 吞异常）；dev compose 同样缺 002 执行步骤，全新环境角色不存在 → dev 审计默认全坏且 /health 还报健康 | `deploy/docker-compose.prod.yml:154-166` + `docker-compose.yml:163` |
| C21 | 网关 JWT_SECRET 有可用的默认回退 `dev-secret-change-me`（auth 侧 fail-fast，网关侧静默回退）→ 漏配时任何人可用公开密钥伪造 admin token | `gateway/app/core/auth_middleware.py:81` |

---

## 3. Major 问题（按域）

### auth-service
- M1 登录失败不落审计（成功才写）→ 暴力破解尝试无痕；未注册用户密码路径不跑 bcrypt → 响应时间差构成时序侧信道枚举
- M2 `_parse_expires` 无校验：`JWT_EXPIRES_IN` 非数字/空串/负值 → 登录 500 或 token 立即过期
- M3 验证码计数非原子（get→自增→setex），并发可绕过耗尽保护
- M4 `X-Forwarded-For` 直接信任 → 审计 IP 可伪造；短信错误消息原文回显给客户端
- M5 users CRUD：username 唯一性非原子、manager_id 无存在校验、phone 无格式校验、status 无枚举校验、`v is not None` 过滤导致字段无法清空、admin 可自伤（把自己降级）
- M6 code 配置项（长度/次数/TTL）无上下界校验，`AUTH_CODE_LENGTH=0` 生成空验证码

### specialist-service
- M7 **流式答案合规审核旁路**：`generate_stream` 边生成边推送，答案审核在全文推送后才执行 → 违规内容已展示，done 帧的掩码文案不是门禁（REST 路径正确）
- M8 降级（qwen）链路：citations 恒空（需求必做引用溯源）、不传 dialog_id（多轮上下文断）、同步阻塞事件循环
- M9 stats：`total_conversations` 双倍计数（每轮落 2 行）、无管理员门禁（任意用户可查）、响应形状三方不一致（后端/mobile/web 三套字段名+语义）
- M10 收藏多轮错配：锚定某轮 conversation_id，但 question/answer 取 session 组第一条 → 收藏展示错对问答
- M11 60 帧硬上限（约 30 分钟无整体超时熔断）；bailian_client 直索引缺安全链（KeyError 非 BailianException 不被捕获）；`tokens_used` 恒 NULL；专员未配 bailian_app_id 返回 500（应 4xx）
- M12 证据等级被动正则且降级模式恒 None；预检拦截不写审计、latency 恒 0
- M13 专员列表把 `bailian_app_id`（百炼凭据）返回给所有登录用户

### visit-service
- M14 pre-visit 的 `_HISTORY_SQL` 无 user_id 校验 → 任何用户可读他人拜访总结/异议/情绪（跨用户敏感数据泄露）
- M15 compliance_client fail-open：合规服务不可用时红线内容静默放行（与"生死线"定位相反；NLS 反而是 fail-closed，行为不对称）
- M16 end_visit AI 降级时写占位串 → 记录永久锁死无法重试，结构化总结永远缺失
- M17 听悟链路：见 C12；`process_transcript` 结果键错位（见 C3）
- M18 异议识别 competition 规则 `用.{0,6}药` 几乎每次拜访误报"竞品对比"
- M19 "录完再推" 16KB×N 分片突发灌入 + 立即 stop 与 NLS 实时流式要求不匹配（设计层问题，真机大概率丢帧）
- M20 其他：`int()`/日期解析未捕获 → 500；WS 无连接数/速率限制；归属校验抛裸 HTTPException(403) 与错误码体系不符；PUT visit/task 无审计日志；follow-up 无状态校验可重复建任务；duration 秒后 end 记 1 分钟

### knowledge-service
- M21 **ES 关键词索引从未写入**：`EsClient.index_doc` 无任何调用方，search 主链路不碰 ES；即使配了 ES_URL 文档也永远不会进 ES（比"未接实例"更深）
- M22 新版本上传先 archive 旧版再 OSS 上传 → 上传失败旧版已归档丢失；审核窗口期旧版不可检索而索引仍含旧内容 → 检索不一致
- M23 approve 中途异常状态卡死 `processing`（无恢复路径）；`reject_document` 无状态校验（可直接驳回已上架文档）且不删索引 → 被驳回文档仍可检索
- M24 上传无扩展名白名单/大小限制、全量读内存；任意类型文件可传 OSS 得公网 URL；审核流权限是 admin/manager/medical 任一 + 可自审
- M25 `review_document`/`upload_document` 在 async 端点同步执行，wait_for_parse 轮询最长 1 小时 → 2 worker 下阻塞整个服务
- M26 未上架文档（draft/rejected/archived）全文（10 万字符）对 rep 开放读取
- M27 降级百炼时 product_id/doc_type 过滤静默丢弃；`_filter_expr` doc_type 单引号不转义（注入使表达式出错 → 跨类型泄露）；DashVector 元数据 product_id 类型不一致（int vs str）
- M28 PG 'simple' 分词不切中文 → ts_rank 恒 0 全靠 ilike 全表扫；score 是伪分数

### compliance-service
- M29 规则 create/update 无字段校验：`rule_type` 拼错静默当语义规则（无 key 永不生效）、`action` 任意值永不拦截、severity 脏值 → **管理员输错一个字段整条规则静默失效**
- M30 patterns 为字符串时被逐字符展开（`"abc"` → `["a","b","c"]`）→ 单字符匹配几乎全量误拦
- M31 `service_name` 存的是内容类型（user_input/ai_output）→ 监管报告"按服务"统计失真
- M32 warn/log 违规也计入"拦截"计数器与 compliance_blocks 表 → 拦截率被污染
- M33 `checked_rules` 是假数据（用全量规则 id 覆盖，含未执行的语义规则）
- M34 /check 的 content 非字符串 → 500；GET /rules、/blocks 无角色限制（rep 可读全部规则规避检查）；规则测试无 key 时语义规则误报"不命中"；report hit_count 不按时间过滤

### audit-service
- M35 导出 `.limit(10000)` 静默截断；无角色限制（rep 可下载全量审计）；导出行为本身不入审计；导出列不含 compliance_result/hashes（"含所有 AI 决策"名不副实）
- M36 stats 缺拦截率（compliance_blocks 有数据未接）与活跃度；before_value 恒空（唯一写入方已坏，见 C7）；after_value 覆盖不全
- M37 时间偏移 8 小时：logger 写 aware UTC 到 naive 列，web 按本地时区渲染 → 所有展示时间偏移 8 小时
- M38 `AUDIT_DATABASE_URL` 缺配回退 medagent 账号 → 002 后写入静默失败（同 C20）；`log()` 无 `**kwargs` 契约脆弱（C7 已实证）；写入失败返回 success("已记录") 误导排查
- M39 查询/详情/stats 无角色限制（rep 可看全量审计）；`keyword` 死参数；`log_batch` 死代码；`AUDIT_LOG_RETENTION_DAYS` 死配置

### hcp-service
- M40 update 用 `hasattr` 放行任意列（mass assignment）：PUT `{"id":999}` 可改主键、`{"created_at":...}` 可伪造时间戳 → 应白名单
- M41 AI 画像无缓存（每次 profile 都付费调 qwen-max，结果也不落库）+ 同步阻塞事件循环（qwen 超时期间整个 worker 卡死）
- M42 内部画像更新接口 tags 直收客户端值，字符串被按字符迭代拆标签（契约脆弱点）；create 未知字段 500/主键抢占；file.filename None → 500；Excel 数值单元格电话带 `.0`；错误行号偏移 1；influence_level 任意值；降级 reason 泄露内部错误

### gateway
- M43 按 user_id 限流是死代码：中间件执行序保证 RateLimiter 先于 Auth 运行，`scope["user"]` 恒空 → 永远走 IP 分支（注释与事实相反）；每 worker 独立限流器（--workers 2 实际限额翻倍）；限流字典无键清理（内存无限增长）
- M44 网关 404/503/504 返回 `{"detail":...}` 破坏统一格式（`resp.data.code` 拿到 undefined）
- M45 只捕获 ConnectError/TimeoutException，上游断连冒泡成 500 纯文本
- M46 JSON 分支透传上游 content-length/content-encoding 可能失配；WS 关闭码语义丢失（4401/4404/4500 → 1000）；/health 是假聚合（从不探测）；PUBLIC_PATHS 前缀匹配过宽；无 X-Forwarded-For 注入（上游审计 IP 全是网关）

### shared/scripts/deploy
- M47 `init_db.sql:173` REVOKE 对 superuser 从未生效（002 已确认）且无"必须执行 002"提示 → 全新环境有"已不可篡改"假象
- M48 002 迁移 `NOSUPERUSER` 后系统无任何 superuser → 后续 CREATE EXTENSION/管理操作无入口且不可恢复
- M49 `tests/e2e_test.py` 调网关内部路径不带 X-Internal-Key → 403 必断；debug_test.py 同样过时 + token payload 字段错
- M50 `deploy/arms-monitor.py` 的 `db_connection_pool_usage` 指标全仓库无服务导出 → 永不告警
- M51 prod compose 其余 7 服务无容器内 DB/Redis URL 覆盖（默认 localhost）→ 按模板部署全连不上；`DB_USER` 可配置但 init_db.sql REVOKE 硬编码 medagent
- M52 `.github/workflows/deploy.yml` 触发分支 `main` 但默认分支是 master → 部署流水线永不触发；ci.yml 无 postgres/redis services（部分测试无法复现）

### web
- M53 401 只处理 401/5xx，403 无处理 → 非 admin 点操作按钮静默失败；菜单/按钮无角色控制
- M54 假数据残留：专员 StatCard 12/10/1342、审计 15,832/423、展开行假 hash、合规趋势 12%；`/health` 不代理 → 网关状态卡恒"不可达"且代码写死 'up'
- M55 仪表盘：用户数/对话量恒 0（分页 bug）；"对话总量"统计参数错（operation vs action）→ 统计的是全量审计
- M56 ModalForm 串台（见 C16）；热更新未 await 未 catch（失败也弹成功）；sorter:true 无后端支持；知识库检索测试若启用必 403（内部路径）

### mobile
- M57 `checkAuth` catch 不分 401 与网络错误 → 启动网络抖动即踢出登录页
- M58 `Alert.prompt` 仅 iOS → **Android 无法添加标签**
- M59 "代表说/医生说"按钮用写死话术真实 POST 落库 → 假对话写入拜访证据库（审计取证污染）
- M60 sendTranscript 失败 catch{} 完全吞掉 → 转写段上屏但后端没收，无提示无重试
- M61 假数据兜底上屏：专员列表假专员"小K"、合规假规则 R001-R007、pre-visit 假画像/话题（与真实数据无标记混用）
- M62 `toISOString().split('T')[0]` 取今天 → 东八区凌晨 0-8 点取昨天，工作台"今日拜访"区间错一天
- M63 聊天流式生成中返回页面不关 WS（连接泄漏、服务端持续生成）；asr/wsChat onerror 后不主动 close
- M64 设置页全部行无 onPress（死行）；Profile 假兜底"肿瘤事业部"；HelpCenter 热线占位；语音输入 stub
- M65 getStats 形状错（死代码未爆）；专员状态枚举错位（draft/active/disabled vs active/inactive/configuring）

---

## 4. 需求未实现 / 未完成功能清单（GAPS）

### 4.1 完全缺失（需求标"必做"）

| 需求点 | 现状 |
|--------|------|
| **飞书批量导入 + 飞书双向同步**（2.2.6 必做） | 全仓库无任何 feishu/larksuite 代码 |
| **知识库关键词索引 ES + 向量+ES 混合检索**（2.2.3 必做） | ES 从未写入（M21）；混合检索是 向量+PG FTS（0.7/0.3），非需求指定 |
| **自动解析：表格识别/图片 OCR/章节识别**（2.2.3 必做） | 只做纯文本抽取，注释明说"表格/OCR 由百炼托管"——必做项降级为依赖付费云解析；旧格式 .doc/.ppt 上传成功但正文恒空 |
| **知识库内容库**（第 12 章：100-300 篇文献、5-15 指南、10-30 法规） | `knowledge-base/` 空目录；`scripts/build_knowledge_base.py` 不存在 |
| **驾驶舱：风险热力图、实时动态**（2.2.7 必做） | web 完全无实现（HeatmapCell 类型定义了但无 UI 无接口） |
| **驾驶舱：满意度指标** | 后端无满意度聚合，web 缺 |
| **实时转写"双方分离"（说话人分离）**（拜访中必做） | NLS 配置无 speaker 分离，回推帧无 speaker 字段，全部标为 rep |
| **登录失败尝试留痕**（2.2.5 全量操作日志） | 密码/验证码失败尝试零审计 |
| **移动端密码登录** | 后端支持，移动端无入口 |
| **移动端：拜访后"确认完成"提交、"模块可编辑"、分享**（3.1.6） | 确认完成无提交动作、分享是"开发中"弹窗 |
| **移动端：关键节点标记、引用资料快捷发送**（3.1.5） | 缺失 |
| **移动端：对话语音输入、长按复制、分享**（3.1.7） | 语音是 stub 弹窗，分享/复制缺失 |
| **移动端：医生搜索"最近浏览/我的医生/字母索引"、快捷操作（打电话/发消息/预约）**（3.1.9/3.1.10） | 缺失 |
| **移动端：内容页"推荐内容/最新内容"** | 缺失 |
| **移动端：合规手册"错误 vs 正确对比、联系方式"**（3.1.13） | 缺失（HelpCenter 零后端调用） |
| **Web：知识库检索测试入口** | 无 UI，且接口本身不可达（C19） |
| **Web：合规拦截记录页** | 无页面（blocks 接口只有 Dashboard 用） |
| **Web：专员数据查看（使用统计/用户反馈 UI）** | stats 接口存在但无 UI；看板是假数据 |
| **Web：话术模板编辑（3.2.3 专员能力配置）** | 无 |
| **Web：用户管理"角色说明"** | 无 |
| **Web：医生 Excel 批量导入 UI** | 后端有 /batch-import，前端无入口 |
| **X-Request-ID 链路追踪**（7.1） | 网关不生成不强制，仅 auth 消费 |

### 4.2 已实现但实际不可用（契约断裂，见 Critical）

- 移动端拜访前准备页（画像/话题/红线/开场白/上次跟进 键错位 + AI 输出中文键无映射层）
- 移动端拜访中异议/合规提醒（C3）、拜访后总结（C2/C4）
- 移动端工作台/拜访详情/我的页展示字段（VisitRecord 全字段错位：日期恒"未排期"、医生名恒"未知医生"）
- Web 专员列表/合规规则/审计查询/用户新增（C13-C16）
- 知识库审核流 UI（pending 状态不存在）
- Web/移动端互动历史、AI 画像（2.3）

### 4.3 部分实现 / 有缺陷

| 需求点 | 现状 |
|--------|------|
| 规则热更新 | 已实现（DB + TTL 60s）✓ |
| 规则在线测试 | 已实现但语义规则无 key 误报"不命中" |
| 拦截记录 | 写入 ✓ 但混入 warn/log 非拦截事件 |
| 监管自查报告导出 | 有（3 sheet）但"按服务"统计失真（M31） |
| 审计高级搜索 | 后端过滤齐全，web 参数全错 → UI 实际不可用 |
| 审计统计图表 | 操作量/趋势真；**拦截率、活跃度缺失** |
| 审计监管报告 | `.limit(10000)` 截断、无角色限制、导出自身不入审计、不含 AI 决策字段 |
| 证据等级标注 | 被动正则提取、降级模式恒 None；eval 维度与实现字段不一致 |
| 引用溯源 | 百炼路径 ✓；降级路径恒空 |
| 多轮会话 | 百炼 dialog_id ✓；降级路径上下文断 |
| 反馈/收藏 | 真落库 ✓；收藏多轮错配（M10）、反馈无去重 |
| 专员数据看板 | stats 计数翻倍、无门禁、三端形状不一致 |
| 版本管理 | DB revision 链有；索引侧旧版永不清理（DashVector 旧 chunk/百炼旧文件） |
| 文档审核流 | 状态机有；权限过宽（admin/manager/medical）+ 可自审 + web 无法操作 |
| 用户反馈（检索） | 真落库但 web/mobile 零调用方，形同虚设 |
| 任务创建 | 仅显式调 /follow-up 才落库，end_visit 不自动触发，无去重 |
| 医生画像更新 | 已实现（超需求）✓ 但失败仅 warning 无重试 |
| 医生批量导入 | 有（行级事务+错误报告）；**无去重、无模板下载**、行号偏移 1 |
| 标签管理 | 后端 ✓；web 接口发错 body 必 422（死代码未爆）、Android 无法添加 |
| 拜访统计接口 | visit-service 无任何 stats 接口 |
| 限流 | 单进程内存版、按 user_id 死代码、每 worker 独立 |
| 监控 | 3 条告警 1 条无指标源；`http_requests_total` 恒 0（REQUESTS 无 .inc() 接线） |
| CI/CD | deploy workflow 永不触发（分支错）；无 lint 步骤（mypy/eslint 带 `|| true`） |
| 代码规范（13 章） | pyproject.toml/.eslintrc 均不存在 |

### 4.4 需求文档滞后项（实现存在但文档未同步）

- users 表 password_hash + 手机号唯一索引（001 迁移）；conversation_feedback/favorites/tasks/knowledge_feedback 4 表；knowledge_documents 的 revision/parent_doc_id 列 —— 需求 6.2 均无
- 4.3 微服务清单缺 auth-service；监控指标名与需求不一致；附录"审计独立库"实为同库低权账号

---

## 5. 已验证的已知问题（CLAUDE.md 记录，确认属实）

- ✅ NLS_APPKEY 未配 fail-closed（asr_ws.py:38-50 + 测试）——但发现"录完突发推流"设计层不匹配（M19）
- ✅ HelpCenter 零后端调用
- ✅ web 系统配置/上传等假动作（升级为 C13-C18 详单）
- ✅ ES 未接（实际更糟：无任何写入方）
- ✅ X-Request-ID 未贯穿、REQUESTS 无 .inc()
- ✅ knowledge-base 空目录
- ✅ 短信默认 console（AliyunSmsSender 实现正确，4 测试全 mock）
- ✅ 未配真实百炼 key 时 WS 未端到端冒烟
- ⚠️ "五屏已接真实数据"部分存疑：列表能出数据，但展示字段大量错位（工作台/详情/我的）

---

## 6. 修复优先级建议

### 第一优先级（阻塞核心用户流程）
1. **修复 `mobile/src/api/visit.ts` 契约**（C1-C4 一组）：visit_id 键、transcript 响应键、去掉 endVisit 双调、删掉 Mock 假摘要兜底 —— 移动端拜访全流程（产品核心场景 A）
2. **统一分页形状**（C2 结构性）：`paginate()` 顶层补 `total/page/page_size` 或前端统一解包 pagination 嵌套 —— 影响 web 6 个列表页 + Dashboard + mobile
3. **修 auth audit_client 签名**（C7）：加 `**kwargs` 或 before_value 参数
4. **修 compliance fail-open 绕过**（C6）：空内容/空 choices/形状错误归入 R999
5. **修 interactions/画像契约**（C3）：hcps.py 返回形状与两端统一；改 `src/api/*.ts` 映射点
6. **修 knowledge/search 鉴权策略**（C19）：服务端补 require_internal_key 并移除 get_current_user，或移出 INTERNAL_PATHS

### 第二优先级（安全）
7. INTERNAL_API_KEY 模板值加入拒绝集合 + 网关 JWT_SECRET 去默认值（C8/C21）
8. manager 自授 admin + RBAC 重读库（C9/C10）
9. 会话历史 IDOR 归属校验（C5）
10. 验证码 off-by-one + exhausted 文案模糊化（C11）
11. visit pre-visit 跨用户数据隔离（M14）；审计查询/导出/规则读取的角色限制（M34/M35/M39）

### 第三优先级（功能补全/契约修复）
12. Web 端 C13-C18 一组：真实接线专员 CRUD/知识库上传/用户表单/审计筛选/导出下载 + ModalForm destroyOnHidden
13. 生产 compose 补 AUDIT_DATABASE_URL + 容器内 DB URL 覆盖 + 002 执行步骤（C20）
14. ES 写入接线或明确移除；知识库审核流 UI 状态对齐
15. 听悟归档解析修复（C12）
16. 按 4.1 清单逐项补功能（飞书、热力图、说话人分离、密码登录等）
17. 收尾：删除 requirements.txt.tmp 等残留、deploy.yml 分支修正、限流器 user_id 分支、arms-monitor 指标、/health 真探活

---

*审计方法说明：11 个独立代理并行逐文件审查（每个代理独立读全其域内文件并交叉核对契约），关键结论（分页形状、visit_id 契约、auth audit_client 签名、compliance fail-open）已人工复核源码确认；compliance 与 auth 两项有实测复现。*
