# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MedAgent 药企 AI 数字员工系统 — 五层架构的医药代表 SaaS 平台，提供数字学术专员、陪访助手、知识库管理、合规审核、审计追溯。七个微服务 + API 网关，部署在阿里云，AI 能力通过百炼多模态交互 App（WebSocket）+ 通义千问（OpenAI 兼容）+ 通义听悟（ASR）提供。

## Architecture

```
Web 管理后台 (React+Vite, web/, :3000) ─┐
                                          ├─→ Gateway (:8000) ─→ 微服务集群
移动端 (React Native, mobile/, 可构建) ────┤
医生端 (React Native, mobile-doctor/, 2026-08-17 一期 B) ─┘
                                              ├─ auth(:8007)      认证 — 手机验证码/密码登录，签发 JWT
                                              ├─ specialist(:8001) 数字专员 — 每个专员=一个百炼多模态App
                                              ├─ visit(:8002)     陪访助手 — 听悟转写+合规实时检查+异议识别
                                              ├─ knowledge(:8003) 知识库管理 — 文档审核流+百炼App知识库同步
                                              ├─ compliance(:8004) 合规审核 — 三层审核(关键词→正则→LLM语义)
                                              ├─ audit(:8005)    审计日志 — 全链路留痕+Excel导出
                                              └─ hcp(:8006)      医生管理 — 档案CRUD+AI画像+Excel批量导入
```

**核心调用链路（数字专员问答）：**
用户提问 → Gateway → specialist → compliance 合规预检 → 百炼App WebSocket 知识检索+生成 → compliance 审核答案 → audit 日志 → 返回

**关键架构决策：** 每个数字专员 = 一个阿里云百炼多模态交互开发套件 App（自带知识库/文档解析/向量化/检索）。业务层不建文档处理流水线，百炼内部消化。陪访助手/医生管理不需要百炼App，全部通过千问直调（`DASHSCOPE_API_KEY`）或调用 specialist 的 chat 接口。

**网关 ROUTE_MAP（main.py）：** 除 7 个服务前缀外，还映射了跨服务路由 —— `/api/v1/conversations`、`/api/v1/favorites`（→specialist）、`/api/v1/tasks`（→visit）、`/api/v1/users`、`/api/v1/qualifications`（→auth）、`/api/v1/nls`（→visit），前端按资源路径访问无需关心服务归属。**2026-08-17 医生端（一期 B）追加**：`/api/v1/medical`、`/api/v1/twin-subscriptions`、`/api/v1/share-links`（→specialist）、`/api/v1/doctors`（→auth，医师认证）。**2026-08-17 分身分享+夜间简报（一期 C）追加**：`/api/v1/briefings`（→specialist，代表端夜间简报查询）。**2026-08-19 合规培训考试（二期 F）追加**：`/api/v1/training-materials`、`/api/v1/exams`（→auth，培训材料/题库考试；承诺书签署走 `/api/v1/qualifications/commitment/*`，复用 qualifications 前缀转发）。**2026-08-19 学术触达（二期 G）追加**：`/api/v1/academic-cards`、`/api/v1/card-pushes`（→specialist，学术卡片生成/推送/医生收件箱/站内通知）。**2026-08-19 AI陪练+Skill模版（二期 H）追加**：`/api/v1/skill-packages`、`/api/v1/practices`（→specialist，Skill 模版管理/审核/广场/加载 + AI 陪练会话/评分；分身风格/启停/生成挂既有 `/api/v1/specialists/{id}/style|pause|resume` 与 `/api/v1/specialists/style-test`）。**2026-08-20 医生端体验（二期 I）追加**：`/api/v1/doctor-profiles`、`/api/v1/patient-edu`、`/api/v1/doctor-plaza`、`/api/v1/doctor-stats`（→specialist，医生偏好引擎/患教工具/医生侧广场/运营统计）。**2026-08-20 Skill 生态闭环（三期 J）追加**：无新前缀——`/api/v1/skill-packages` 下 release/mine/asset-list/{id}/off-shelf 复用既有 skill-packages 前缀（→specialist），`/{id}/detail` 补访问审计（见下方三期 J 补记段）。**2026-08-20 患教专区审核流（三期 M）追加**：无新前缀——`/api/v1/patient-edu` 下 `{id}/publish`、`{id}/unpublish`、`review-queue`、`{id}/review`、`zone` 复用既有 patient-edu 前缀（→specialist）。**120s 超时 carve-out**：`api/v1/knowledge/`、`api/v1/qualifications/`、`api/v1/doctors/` 三前缀（百炼导入/证书 OSS 上传慢时防 30s 网关先断）。

**2026-08-11 审计补记的服务端点（此前未入文档）**：audit `GET /api/v1/audit/stats`（仪表盘聚合：总数/风险分布/服务分布/按日趋势）、hcp `POST/DELETE /api/v1/hcps/{hcp_id}/tags`（标签增删）、visit `GET /api/v1/tasks` + `PUT /api/v1/tasks/{task_id}` + `GET /api/v1/visits/{visit_id}/tasks`（tasks 模块，follow_up 自动建任务后管理）、compliance `POST /api/v1/compliance/rules/test`（规则试跑）与 `GET /api/v1/compliance/redlines`（见 Compliance Rules 章节）、visit `GET /api/v1/nls/tts-token`（TTS 合成凭证：require_roles rep/admin/manager；未配 NLS_APPKEY → BusinessError 4xxx；移动端 TTS 凭证）。

**2026-08-17 备案资质子系统补记的服务端点（一期 A，此前未入文档）**：auth `POST /api/v1/qualifications`（代表提交备案资质，multipart：学历/培训证明文件 + filing_number/filing_expire_date，仅 rep 可提交，审计 action=qualification_submit）、`GET /api/v1/qualifications/me`（代表查本人备案状态，filing_status 为派生值 not_filed/valid/expired）、`GET /api/v1/qualifications`（分页列表，audit_status/filing_status/keyword 过滤，含 rep_name）、`PUT /api/v1/qualifications/{id}/review`（资质审核 approve/reject，require_roles admin/manager/compliance/medical，审计 action=qualification_review）。

**2026-08-17 医生端子系统补记的服务端点（一期 B，此前未入文档）**：auth `POST /api/v1/doctors/certs`（医生提交执业资质 multipart：cert_image + cert_type ∈ {physician, practice}，仅 role=doctor，提交重置 cert_status=pending，审计 action=doctor_cert_submit）、`GET /api/v1/doctors/certs/me`（任意登录查本人资质，无记录返回 null）、`GET /api/v1/doctors/certs?page&page_size&cert_status&keyword`（管理分页列表，require_roles admin/manager/compliance/medical，items 含 doctor_name/doctor_phone）、`PUT /api/v1/doctors/certs/{id}/review`（资质审核 approve/reject，驳回必填 reason，仅 pending 可审，审计 action=doctor_cert_review）；specialist `POST /api/v1/medical/qa`（医生端医学问答：search-internal 检索 → qwen 生成（仅基于片段作答+逐条引用）→ 问题/答案合规双检 → 审计；任意登录用户可用，返回 {answer, citations, disclaimer, blocked, violations, knowledge_empty}）、`POST /api/v1/twin-subscriptions`（订阅分身：twin 必须 active、consent_agreed 必 True，写 DoctorConsent 留痕 + 订阅行，同 twin 幂等）、`GET /api/v1/twin-subscriptions`（本人订阅列表，join 分身名/状态）、`POST /api/v1/twin-subscriptions/{twin_id}/toggle`（屏蔽/恢复 status subscribed/blocked）、`POST /api/v1/share-links/{token}/activate`（分享链接激活：token 不存在/过期 4001；返回 {twin, subscribed, subscription_status}）；knowledge `POST /api/v1/knowledge/search-internal`（服务间检索：require_internal_key + 网关 INTERNAL_PATHS 双重校验，body/校验/返回与 /search 同款）。

**2026-08-17 分身分享+夜间简报子系统补记的服务端点（一期 C，此前未入文档）**：specialist `POST /api/v1/share-links`（rep 生成分享链接：twin_id 必须 active、expire_days 1-365 可空=永久、url_token uuid4、share_url=medagent-doctor://twin/{token}，审计 action=twin_share_link_create）、`GET /api/v1/share-links`（rep 本人链接列表，join 分身名，按 id 倒序）、`GET /api/v1/briefings?page&page_size`（rep 夜间简报分页列表，join 分身名，按 briefing_date 倒序）、`GET /api/v1/briefings/{briefing_id}`（rep 简报详情，按 representative_id 归属校验，越权/不存在 4001）；`POST /api/v1/share-links/{token}/activate` 一期 C 起每次激活 add_count+1（含重复激活，口径=被添加次数，见一期 B 段）。

**2026-08-19 合规培训考试子系统补记的服务端点（二期 F，此前未入文档）**：auth `POST/GET/PUT/DELETE /api/v1/training-materials`（培训材料 CRUD + 分页列表；创建/改/删 require_roles admin/manager/compliance/medical，列表/详情任意登录用户可读，archived 软删不展示；material_type ∈ regulation/rdpac/internal）、`POST/GET /api/v1/exams/questions` + `PUT /api/v1/exams/questions/{id}` + `POST /api/v1/exams/questions/{id}/review`（题库 CRUD + 人工审核，全 require_roles admin/manager/compliance/medical；`answer` 仅管理端 expose_answer 可见、代表端永不返回；approved 题不可改，编辑后重置 pending 重新送审）、`POST /api/v1/exams/questions/ai-generate`（AI 出题草稿，require_roles 同上；material_id 必 active，count 1-20；草稿不落库、逐条 `_validate_question` 不合规跳过；依赖 `DASHSCOPE_API_KEY` + `QWEN_EXAM_MODEL` 默认 qwen-turbo）、`POST /api/v1/exams/start`（rep 开考：approved 题随机抽，默认 10 最多 30，不含答案）、`POST /api/v1/exams/submit`（rep 交卷：判分集合相等 → 写 exam_records + 回写 representative_qualifications 三字段——仅更高分覆盖 exam_score、passed 才置 training_completed；及格线 `EXAM_PASS_SCORE` 默认 80）、`GET /api/v1/exams/records/me`（rep 本人记录分页）+ `GET /api/v1/exams/records`（管理端全量分页）、`POST /api/v1/qualifications/commitment/send-code`（rep 发签署验证码，复用 auth CodeStore + 短信通道，审计 commitment_send_code）+ `POST /api/v1/qualifications/commitment/sign`（rep 校验验证码 → commitment_signed=true + 审计 commitment_signed，需先有备案资质）。

**2026-08-19 合规风控深化子系统补记的服务端点（二期 E，此前未入文档）**：compliance `GET /api/v1/compliance/daily-summary|trends`（见 Compliance Rules 章节；**拦截口径=action='reject'，warn/log 不计入**）；specialist `GET /api/v1/conversations/search`（对话日志全文检索，require_roles admin/manager/compliance：keyword 全文 ILIKE + user_id/specialist_id/date_from/date_to 过滤，每条命中带该 session 完整上下文 `context`，`blocked` 取 conversations.compliance_result）、`GET /api/v1/specialists/monitor`（分身监控分页列表，require_roles admin/manager/compliance/medical：status/official 过滤 + today_services/avg_latency_ms/service_doctors/added_count/compliance_health/approval_rate 统计字段，分批聚合避免 N+1）、`GET /api/v1/specialists/review-queue`（**分身维度**待复核名单，require_roles admin/manager/compliance：按 conversations.compliance_result.blocked=true 近 24h 按 specialist_id 聚合 ≥5，返回 specialist_id/name/rep_name/block_count；**不做自动冻结**）、`POST /api/v1/specialists/{id}/freeze`（合规冻结，require_roles admin/manager/compliance，reason 必填 + 审计 specialist_freeze；已冻结再冻 4001）、`POST /api/v1/specialists/{id}/unfreeze`（解冻 frozen→active + 审计 specialist_unfreeze；非 frozen 解冻 4001）。**status 值域扩为 draft/active/disabled/frozen**（VALID_STATUSES 新增 frozen）；`POST /api/v1/specialists/{id}/chat` **仅 status=active 可对话**（frozen 与 disabled 一样 404「专员不存在或已停用」）。digital_specialists 新增 is_official/representative_id（迁移 014，见 Database 章节；官方公共数字员工 is_official=true 且 representative_id 须为空，绑定代表会被 ParamError 拒绝）。

**2026-08-19 学术触达子系统补记的服务端点（二期 G，此前未入文档）**：specialist `POST /api/v1/academic-cards`（rep 生成学术卡片：AI 生成——qwen-max 直调 + 知识库检索引用（top_k=3）+ 独立 JSON 契约 {conclusion, key_points[], summary, citations[]}，不依赖 medical 的 _qwen_json；内容包裹 `<user_content>` 定界防注入，对齐 S7/M7 口径；三层合规预检 fail-closed，命中即按 violations[0].rule_code 拦截 ParamError；落库 is_ai_generated=true / compliance_status=passed / status=active，审计 action=academic_card_create）、`GET /api/v1/academic-cards`（rep 本人 active 卡片分页，id 倒序）、`GET /api/v1/academic-cards/stats`（学术内容触达统计，require_roles admin/manager/compliance/medical：days 默认 30，返回 total_pushes / total_reads / **read_rate = total_reads/total_pushes（0-1 小数，round 4）** / rep_ranking top10）、`POST /api/v1/academic-cards/{card_id}/push`（rep 推送，body doctor_ids 数组 ≤50；**推送对象口径 = doctor_twin_subscriptions 中 status='subscribed' 且 twin_id ∈ 该代表分身（Specialist.representative_id=本人）的 doctor**；同 card_id+doctor_id 已存在则幂等跳过；每条写 card_push_records（**含 specialist_id=该医生订阅的代表分身**）+ notifications type=card_new link=/card-pushes，返回 {pushed, skipped}）；`GET /api/v1/card-pushes`（医生端收件箱，require_roles doctor，items 带 card 完整内容）、`POST /api/v1/card-pushes/{push_id}/track`（阅读追踪：read_status ∈ unread/read/favorited/forwarded + read_at + tracked_seconds，越权/不存在 4001）、`POST /api/v1/card-pushes/{push_id}/feedback`（医生反馈 ≤500 字符：useful→read_status=favorited / useless→read / 追问文本；回流代表站内通知 type=card_feedback/card_question，link 指向 /briefings；**useful 另写 conversation_feedback(rating=1, specialist_id=push.specialist_id, user_id=doctor, conversation_id=None) 计入分身好评率 approval_rate，同 push 去重不重复写**）、`GET /api/v1/card-pushes/notifications`（站内通知分页，require_roles rep/doctor，按 user_id 过滤）。**简报就绪通知（一期 C 挂账的简报真实通知渠道，本计划落地）**：nightly_briefings 生成时写 notifications type=briefing_ready（title=你的夜间简报已生成、content=查看医生提问汇总与需跟进事项、link=/briefings，见 briefing_generator.py）。

**2026-08-19 AI陪练+Skill模版子系统补记的服务端点（二期 H，此前未入文档）**：specialist `POST /api/v1/skill-packages`（创建 Skill 模版，require_roles admin/manager/compliance/medical；name ≤100 + skill_weights 非空对象必填，audit_status=pending，审计 action=skill_create）、`GET /api/v1/skill-packages`（管理分页列表，require_roles 同上，audit_status 过滤，**`to_dict()` 默认不含 skill_weights**）、`GET /api/v1/skill-packages/public`（代表侧广场，require_roles rep，仅 approved+is_public，按 heat 倒序，无 skill_weights）、`GET /api/v1/skill-packages/{id}/detail`（审核详情，require_roles admin/manager/compliance/medical，`expose_weights=True` 受控查看 skill_weights）、`POST /api/v1/skill-packages/{id}/review`（approve/reject，仅 pending 可审，reject 必填 reason ≤500，写 skill_audits + 审计 action=skill_review）、`POST /api/v1/skill-packages/{id}/load`（代表加载 Skill 到陪练场，仅 approved+is_public，heat++）；`POST /api/v1/practices`（rep 创建陪练会话，scenario 必填 ≤100，skill_id 须 approved+is_public）、`POST /api/v1/practices/{id}/turn`（rep 多轮对话：消息合规预检 fail-closed → 注入该场景 approved 异议话术（3.2(5)，无命中回退自由生成）→ qwen-turbo 生成 AI 医生回应 + turn_count++，**history 恒传空**）、`POST /api/v1/practices/{id}/complete`（rep 结束：轮数确定性评分 {evidence_accuracy/objection_handling/communication_logic/overall + per_turn[]} → status=completed + 审计 action=practice_complete）、`GET /api/v1/practices`（rep 本人会话分页）、`GET /api/v1/practices/progress`（rep 进步曲线：聚合本人 completed 会话，返回 {total_sessions,avg_overall,trend[]}）；`POST /api/v1/practices/objection-scripts`（管理四角色创建异议话术 pending，审计 objection_script_create）、`GET /api/v1/practices/objection-scripts`（管理端列表，review_status/scenario_type 筛选）、`POST /api/v1/practices/objection-scripts/{id}/review`（approve/reject，reject 必填 reason，仅 pending 可审，审计 objection_script_review）；`PUT /api/v1/specialists/{id}/style`（分身风格设置，写 persona.style，归属校验本人或 admin/manager，formal_level/reply_length/opening_mode 白名单）、`POST /api/v1/specialists/{id}/pause`（暂停本人分身 status→paused，仅 active 可暂停）、`POST /api/v1/specialists/{id}/resume`（paused→active）、`POST /api/v1/specialists/style-test`（分身生成：风格测试 5 题 answers 数组 → 均值映射 persona.style → 建 active 分身，prompt/检索级个性化非微调）。**status 值域扩为 draft/active/disabled/frozen/paused**（VALID_STATUSES 仍四值用于 CRUD 校验，paused 由 pause 直接写）；`POST /api/v1/specialists/{id}/chat` **仅 status=active 可对话**（paused 与 frozen/disabled 一样 404「专员不存在或已停用」）。

**2026-08-20 医生端体验子系统补记的服务端点（二期 I，此前未入文档）**：specialist `GET/PUT /api/v1/doctor-profiles` + `POST /api/v1/doctor-profiles/learn` + `GET /api/v1/doctor-profiles/briefing`（医生学术偏好引擎，require_roles doctor，仅本人可查改；learn 从本人对话历史自动学习（doc_type 从问题文本关键词推断；未按 session_id=medical_qa 过滤，见 Known Gaps）——interest_areas 关键词映射 + preferred_style 平均回答长度推断，closed=true 关闭个性化时不学习；briefing 个性化学术简报为简化版——按兴趣领域返回关键词建议 {items:[{area,suggestion,doc_type}],personalized}，非真实内容聚合）；`POST/GET /api/v1/patient-edu/templates` + `POST /api/v1/patient-edu/templates/{template_id}/review`（患教模板 CRUD+审核，创建/审核 require_roles admin/manager/compliance/medical，医生端列表仅 approved；驳回必填 reason ≤500）；`POST /api/v1/patient-edu/generate`（医生选 approved 模板 AI 生成患教卡片：qwen-turbo JSON 契约 {title,body,notes,seek_care} + 合规预检 fail-closed + 落库 edu_content_records is_ai_generated=true/visibility=private 默认仅本人可见，不采集患者数据）；`GET /api/v1/patient-edu/mine`（医生本人患教记录分页）；`GET /api/v1/doctor-plaza`（医生侧官方公共数字员工列表，require_roles doctor，仅 is_official+active，附 added_count 被添加数）；`POST /api/v1/doctor-plaza/{twin_id}/subscribe`（添加官方分身：consent 必 True 知情同意 + 写 DoctorTwinSubscription subscribed + DoctorConsent 留痕，幂等）；`GET /api/v1/doctor-stats/activity`（医生活跃度 dau/wau/mau，require_roles admin/manager/compliance/medical）；`GET /api/v1/doctor-stats/twin-ranking`（数字分身使用排行 Top10：added_count 订阅数降序 + approval_rate 好评率）。**chat 订阅硬校验（一期 B 挂账收尾）**：doctor 角色 chat 前必须已订阅该分身——REST `POST /api/v1/specialists/{id}/chat` 未订阅抛 PermissionError 3000「请先添加该分身再对话」；WS `/ws/specialists/{id}/chat` 未订阅关 4403「未订阅该分身」。

**2026-08-20 Skill 生态闭环子系统补记的服务端点（三期 J，此前未入文档）**：specialist `POST /api/v1/skill-packages/release`（rep 发布个人 Skill 到公共空间：name ≤100 / description 必填 ≤200 / content 必填 / skill_weights 非空对象，is_public=True（发布意图）+ audit_status=pending + heat=0，审计 action=skill_release，返回 `to_dict()` **不含 content/skill_weights**）、`GET /api/v1/skill-packages/mine`（rep 本人发布列表分页，creator_id=本人、id 倒序，含 heat/approval_rate/审核状态，不含 content/skill_weights）、`GET /api/v1/skill-packages/asset-list`（管理四角色 Skill 资产公共列表，audit_status/off_shelf_status/keyword 过滤，outerjoin users 返回 creator_name/creator_role，**绝不含 content/skill_weights**）、`POST /api/v1/skill-packages/{id}/off-shelf`（下架：type ∈ compliance|author 白名单，reason 必填 ≤500，写 skill_packages off_shelf_* 五列 + 落库 skill_off_shelves 存档 + 审计 action=skill_off_shelf；**compliance 下架禁用已加载陪练**（`practice_turn` 拦截存量会话），author 下架已加载不受影响、仅新用户不可加载（`create_session` 拦截）；`/public` 与 `/load` 均加 `off_shelf_status == "active"` 过滤）、`GET /api/v1/skill-packages/{id}/detail`（每次查看写 action=skill_detail_view 访问审计，expose_weights=True 受控查看 content/skill_weights）。

**2026-08-20 患教专区审核流子系统补记的服务端点（三期 M，此前未入文档）**：specialist `POST /api/v1/patient-edu/{id}/publish`（doctor 分享到患教专区：visibility→shared + audit_status→pending 进入审核流，仅本人记录可分享、已在审核流 4001、审计 action=edu_publish；**本人使用与站外转发不经此审核流**）、`POST /api/v1/patient-edu/{id}/unpublish`（doctor 撤回分享：visibility→private + audit_status→NULL，含已 approved 内容撤回后专区不可见、未分享 4001、审计 action=edu_unpublish）、`GET /api/v1/patient-edu/review-queue`（管理四角色 admin/manager/compliance/medical 患教内容审核队列：audit_status=pending，outerjoin users 返回 doctor_name，按 id 倒序分页）、`POST /api/v1/patient-edu/{id}/review`（approve/reject，reject 必填 reason ≤500，仅 pending 可审，审计 action=edu_review）、`GET /api/v1/patient-edu/zone`（医生端患教专区浏览，require_roles doctor，仅 visibility=shared 且 audit_status=approved 可见，按 id 倒序分页）。

## Commands

```bash
# 启动基础设施
docker-compose up -d postgres redis          # 先启数据库
docker exec -i medagent-postgres psql -U medagent medagent < scripts/init_db.sql  # 首次初始化

# 设置管理员密码（仓库里不放默认口令，必须跑一次才能登录）
python scripts/seed_admin.py                 # 随机生成并打印一次
python scripts/seed_admin.py --phone 13812345678   # 顺便设手机号（验证码登录需要）

# 旧库升级（补 users.password_hash + 手机号唯一索引）
docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/001_add_user_password.sql

# 审计不可篡改落地（低权账号 + owner 分离 + medagent 降 superuser；只跑一次，密码必传）
docker exec -i medagent-postgres psql -U medagent medagent \
  -v audit_password='<强密码>' < scripts/migrations/002_audit_immutable.sql

# 前端（web/ 管理后台）
cd web && npm install
cd web && npm run dev              # http://localhost:3000，/api 代理到网关 localhost:8000
cd web && npm run build            # tsc -b && vite build

# 运行单个服务
cd services/specialist-service && python -m uvicorn app.main:app --port 8001 --reload

# 运行测试（必须在服务目录下运行，sys.path 依赖 cwd；2026-08-20 二期 I 全量回归后 822 passed = 8 服务 803 + shared 19，auth 另有 7 skipped——本机 Redis 未起，7 个 Lua 并发用例跳过）
cd services/auth-service && python -m pytest tests/ -v        # 135 passed（2026-08-19 二期 E 全量回归实测，本机 Redis 已起；Redis 未起时 128 passed + 7 skipped——7 个跳过为验证码并发 consume Lua 用例；含备案资质 / 医生认证 / 培训材料 test_training_materials 8 / 题库考试 test_exams 19（二期 F 修复 fae0777 补 test_list_questions_exposes_answer_to_admin）/ 承诺书 test_commitment 4 用例）
cd services/specialist-service && python -m pytest tests/ -v  # 252 passed（2026-08-20 三期 M Task 8 全量回归实测；三期 J 终审 239 + 三期 M 患教审核流 13（audit_status to_dict 1 / publish·unpublish 5 / review-queue·review 5 / zone 2）；219（二期 I：198 + 医生偏好 test_doctor_profiles 6 / 患教 test_patient_edu 5 / 广场 test_doctor_plaza 4 + chat 订阅硬校验 test_chat_subscription 3 + 运营统计 test_doctor_stats 3）+ 三期 J to_dict 1 / release·mine 5 / asset-list·detail·public·load 5 / off-shelf·陪练禁用 7；含一期 C 反馈明细/流式门禁全量帧/降级多轮上下文/医学问答/分享简报 + 二期 E 对话全文检索 test_conv_search 5 / 分身监控统计 test_monitor_specialists 9 / 冻结解冻/review-queue + 二期 G 学术卡片 test_academic_cards 6 / 卡片推送 test_card_pushes 7 + 二期 H Skill 模版 test_skill_packages 9 / AI 陪练 test_practices 9 / 分身管理 test_twin_manage 5）
cd services/hcp-service && python -m pytest tests/ -v         # 54
cd services/visit-service && python -m pytest tests/ -v       # 115（含取消/结束态拦截/直调 qwen/转写去重/ASR 连接限制/full_transcript 前缀/结构化合规/prompt 定界）
cd services/compliance-service && python -m pytest tests/ -v  # 107（含 R008-R011 命中/fast 跳过 7 用例/语义网络错误 fail-closed/禁用规则生效/参数健壮性/Unicode 归一化 + 二期 E 聚合日报/趋势 test_monitor 3——待复核名单已移至 specialist，二期 E 终审 7cc85d1）
cd services/knowledge-service && python -m pytest tests/ -v   # 72 passed（2026-08-17 一期 C 收尾实测；ES 检索 status 过滤/索引后置写入/上传校验/search-internal）
cd services/audit-service && python -m pytest tests/ -v       # 26
cd services/gateway && python -m pytest tests/ -v             # 82 passed（2026-08-17 一期 C 收尾实测；CORS 白名单/WS 首帧鉴权/信任代理/路径 dot-segment 拒绝/qualifications 超时 carve-out/medical、share-links、doctors、briefings 转发）
cd shared && python -m pytest common/tests/ -v                # shared 层自测（test_internal_auth.py）

# 运行 A 的 AI 评估（需要真实百炼 App）
cd services/specialist-service && python tests/eval_specialist.py --app-id <百炼AppId>

# 联调冒烟（runbook 第 3 节：登录/专员/对话/R001/R003/审计，全走网关）
python scripts/smoke_runbook.py            # 需根 .env 的 INTERNAL_API_KEY + AUTH_DEV_MODE=true（验证码响应回传）+ SMOKE_PHONE（已注册手机号，未设则直接报错退出）
# 百炼 WS 协议探针（诊断 App 发布状态/返回帧：直连 dump Started→Listening→RespondingContent）
python scripts/probe_bailian_ws.py [app_id]
# 知识库示例文档种子（3 个 txt 上架 → 向量化；离线上架，可用于无真实文献时联调检索）
python scripts/seed_demo_docs.py
# 培训考试种子（内置 2 材料 + 2 approved 题；依赖真实 PostgreSQL，需先跑迁移 013）
python scripts/seed_training_materials.py

# 全部 8 个服务同时启动
docker-compose up -d

# ⚠️ 本机 Docker Hub 不可达（直连超时，需 127.0.0.1:7897 代理）：
#    8 个服务镜像从未构建过（python:3.11-slim 拉不下来）→ 用 native 直跑路径：
docker-compose up -d postgres redis        # postgres/redis 镜像本地已有，可正常起
# 然后每个服务目录下直跑（.env 里 DATABASE_URL 等就是宿主连接配置）：
cd services/auth-service && python -m uvicorn app.main:app --port 8007
cd services/gateway && python -m uvicorn app.main:app --port 8000
# 端口：auth 8007 / specialist 8001 / visit 8002 / knowledge 8003 /
#       compliance 8004 / audit 8005 / hcp 8006 / gateway 8000
# 全量启动参考：logs/native/ 下各服务日志；验证码在 logs/native/auth-service.log（ConsoleSender）

# 单独构建某个镜像：build context 必须是仓库根目录（镜像要 COPY shared/）
docker build -f services/auth-service/Dockerfile -t medagent/auth-service .

# 部署/CI 相关（deploy/ + scripts/ 下，CLAUDE.md 2026-08-11 补记；2026-08-13 更新）
#   deploy/docker-compose.prod.yml   生产 compose（DB_USER/DB_PASSWORD/REDIS_PASSWORD/AUDIT_DB_PASSWORD 必填校验；
#                                    env_file 为 ../.env（仓库根）；仓库根运行：docker compose --env-file .env -f deploy/docker-compose.prod.yml up -d）
#   deploy/arms-monitor.py           ARMS 监控上报（RPC 签名，HMAC 密钥 = AK Secret + "&"，--dry-run；2026-08-13 起
#                                    告警规则真实落地：PromQL Expression + List 同名则 Update 幂等；ClusterId 用 ARMS_CLUSTER_ID）
#   deploy/arms-alerts.yaml          ARMS 告警规则源文件（只保留有真实指标源的规则）
#   scripts/ci-pipeline.yaml         阿里云云效 Flow 流水线（2026-08-13 重写为合法 Flow YAML：version v1.0/stages 映射式/
#                                     needs 依赖，lint 真实生效，test 覆盖 8 服务+shared+web build+mobile jest）
#   scripts/docker-verify.sh Docker 验证脚本（8 服务含 auth）；scripts/smoke_runbook.py 冒烟（2026-08-13 起 R001/R003
#                                    真断言 blocked/violations，任一节失败非零退出，不再恒绿）

# 数据库备份/恢复（详见下方 "Backup & Restore" 小节）
python scripts/backup_db.py --local-only          # 本机备份+校验（开发）；ECS cron 每日 02:00 全流程
python scripts/restore_db.py --source local --yes # 恢复到临时库验证可恢复性
python scripts/restore_db.py --source oss --yes   # 从 OSS 取最近备份恢复（生产恢复演练）
```

**运行测试必须在服务目录下执行** — 所有测试用 `sys.path.insert(0, ...)` 回溯三层找到 shared 模块，路径依赖 cwd。

## Shared Layer (`shared/`)

所有微服务共用。统一响应格式：

```python
from shared.common.response import success, error, ParamError, AuthError, BusinessError
# success(data) → {"code":0,"message":"success","data":{...}}
# raise ParamError("question 不能为空") → {"code":1000,"message":"question 不能为空"}

from shared.common.auth import get_current_user, create_token, require_roles
# @router.get("/xxx") → async def api(current_user: dict = Depends(get_current_user)): ...
# @router.post("/rules") → async def api(current_user: dict = Depends(require_roles("admin", "manager"))): ...
#   require_roles 未登录 401、角色不符 403（code 3000）。角色：admin/manager/rep/compliance/medical/finance/doctor（doctor 为 2026-08-17 医生端新增，见 auth users.py VALID_ROLES）
#   （2026-08-11）受限端点**每次实时查库**（注入 db 会话）：token 里的 role/status 只是登录时刻快照
#   （最长 7 天），降级或停用后旧 token 立即失效——账号不存在/status != active → 403 "账号不存在或已停用"；
#   角色不符 → 403 "无权限"；403 统一抛 PermissionError（AppError）走共享 exception_handler 渲染 {code, message, data}

from shared.common.db_session import get_db
# async def api(db: Session = Depends(get_db)): ...

from shared.common.pagination import paginate, PaginationParams
from shared.common.exception_handler import register_exception_handlers
# register_exception_handlers(app)  # 在 main.py 中注册，自动转换 AppError → 统一响应

from shared.models.base import Base, TimestampMixin  # ORM 基类（id, created_at, updated_at）
```

错误码区间：1000-1999 参数 / 2000-2999 认证 / 3000-3999 权限 / 4000-4999 业务（含合规拦截）/ 5000-5999 系统 / 6000-6999 第三方。

shared 层自带测试 `shared/common/tests/`（test_internal_auth.py + test_exception_handler.py + conftest.py），从 `shared/` 目录跑：`python -m pytest common/tests/ -v`。

**统一错误渲染（2026-08-13 低危批 S1）**：`register_exception_handlers(app)` 现还注册 HTTPException 与 RequestValidationError 两个处理器——7 个业务服务的 404/422 等全部渲染为 `{code,message,data}`（HTTPException 的 detail 若为含 `code` 键的 dict 则原样透传，保住 auth 2001/2002/2003 与 internal_auth 3001 语义；否则按状态码映射：400→1000/401→2000/403→3000/404→4000/405→1000/429→5003/500→5000；422→code 1000）。**gateway 不注册**（有自身渲染，错误码 5001-5005）。

## main.py 标准模板

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.common.exception_handler import register_exception_handlers
from app.config import settings

app = FastAPI(title="MedAgent - XXX服务", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
register_exception_handlers(app)

from app.api.xxx import router
app.include_router(router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": "1.0.0"}
```

## Authentication

`auth-service`(:8007) 是唯一签发 JWT 的地方，两种登录方式共用一个 `/login`：

```
POST /api/v1/auth/send-code   {"phone":"138..."}                    → {expire_seconds}
POST /api/v1/auth/login       {"phone":"138...","code":"123456"}     → {token, user}   # 移动端
POST /api/v1/auth/login       {"username":"admin","password":"..."}  → {token, user}   # Web 后台
GET  /api/v1/auth/profile     (Bearer token)                        → user            # 移动端
GET  /api/v1/auth/me          (Bearer token)                        → user            # Web 后台，同一实现
```

约定：
- 错误信息统一模糊化（不区分"用户不存在"和"凭证错误"），避免账号枚举。
- 验证码一次性、5 分钟过期、60 秒重发冷却、单码最多校验 5 次（第 5 次仍有效，之后作废；用尽后响应文案与通用登录失败一致，防注册状态枚举）。
- `users.password_hash` 为 NULL 表示未设密码，任何密码都登录不了。用 `scripts/seed_admin.py` 设置。
- `profile`/`me` 每次从库里重读用户，被停用的账号即便持有有效 token 也会被拒。
- 短信通道可插拔（`app/services/sms.py`）：默认 `console` 只写日志；阿里云通道已实现（`AliyunSmsSender` 走 dysmsapi，缺 `AUTH_SMS_SIGN_NAME`/`AUTH_SMS_TEMPLATE_CODE` 或 `ALIYUN_ACCESS_KEY_ID`/`SECRET` 时构造即抛 `SmsSendError` fail-fast；配齐后 `AUTH_SMS_PROVIDER=aliyun` 生效，模板变量固定为 `{"code": ...}`）。

## Service-to-Service Communication

所有服务间调用**走 Gateway（`GATEWAY_URL`，默认 `http://localhost:8000`）**，不走直连端口。网关对三类路径区别对待（`auth_middleware.py`）：

```
# INTERNAL_PATHS —— 免 JWT，但必须带 X-Internal-Key 头（否则 403）
POST /api/v1/compliance/check
POST /api/v1/audit/log
POST /api/v1/hcps/profile-update
POST /api/v1/knowledge/search-internal  # 2026-08-17 医生端医学问答检索（specialist→knowledge）
# PUBLIC_PATHS —— 真正公开（免 JWT 免 key）
POST /api/v1/auth/login
POST /api/v1/auth/send-code
# 另有 /health、/docs、/openapi.json、/redoc（网关自身路径；M11 缺口即指未认证可经 `..` 归一化拉 7 个后端 /docs/metrics）
```
（2026-08-06：`/api/v1/knowledge/search` 已移出 INTERNAL_PATHS —— 它是 web 检索的用户向接口，服务端挂 JWT 鉴权；`hcps/profile-update` 是 visit→hcp 的内部接口，双重校验齐全。）

- 内部接口是**双重校验**：网关要求 `X-Internal-Key`（`shared/common/internal_auth.py`），服务端路由还挂 `Depends(require_internal_key)` —— 防 8001-8006 端口直连绕过（历史上 audit/log 可被未认证者直接伪造）。
- 服务间客户端统一用 `internal_headers()` 加头（auth/specialist/visit/hcp 的 audit_client、compliance_client 都已接）。
- `INTERNAL_PATHS` 用"精确匹配或子路径"（`p + "/"`），不会像前缀匹配那样把 `/api/v1/audit/logs` 误判为内部路径；`PUBLIC_PATHS` 仍是前缀匹配，加条目前先确认不会顺带放开别的路由。`/api/v1/auth/profile` 和 `/api/v1/auth/me` 需要携带 token。

调用模式（内部客户端统一写法）：

```python
from shared.common.internal_auth import internal_headers
import httpx
async with httpx.AsyncClient(timeout=10.0) as client:
    resp = await client.post(
        f"{GATEWAY_URL}/api/v1/compliance/check",
        headers=internal_headers(),
        json={...},
    )
    return resp.json()["data"]
```

**降级策略：** 外部服务不可用时不得阻塞业务。合规客户端 fail-open（放行），审计客户端 fail-silent（记日志返回None），specialist 客户端返回 `degraded=True`。

## Database

PostgreSQL（Docker `postgres:15`），**27 张表**均在 `scripts/init_db.sql` 定义（users / products / digital_specialists / hcps / visit_records / conversations / knowledge_documents / audit_logs / compliance_rules / compliance_blocks / conversation_feedback / conversation_favorites / tasks / knowledge_feedback —— 后 4 张由迁移 003 补齐，已并入 init_db.sql；`visit_records.key_nodes`（006）与 `visit_records.status`（008）两列 2026-08-13 起也已并入 init_db.sql，旧库仍须按序执行 006/008）。**`representative_qualifications`（迁移 009，2026-08-17 备案资质子系统，已并入 init_db.sql）**：15 列（含二期预留的 compliance_training_completed / compliance_exam_score / commitment_signed，本计划只建列不接线）；**`filing_status` 是派生值不落库**，由 filing_number + filing_expire_date 计算（not_filed/valid/expired），见 `shared/models/qualification.py`；索引 idx_qual_audit_status / idx_qual_expire。旧库须执行 009。**`doctor_certifications` / `doctor_twin_subscriptions` / `doctor_consents` / `share_links`（迁移 011，2026-08-17 医生端一期 B，已并入 init_db.sql，模型在 `shared/models/doctor.py`）**：医师认证（doctor_id UNIQUE FK users、cert_type physician/practice、cert_image_url OSS、cert_status pending/approved/rejected、reject_reason/reviewed_by/reviewed_at）、分身订阅（UNIQUE(doctor_id,twin_id) uq_doctor_twin、status subscribed/blocked、consent_version/consent_at）、知情同意留痕（twin_id 可空=平台级、consent_type/version/agreed_at）、分享链接（url_token UNIQUE、created_by、expire_at 可空——B 只建表做激活接收侧，链接生成/追踪留 C 计划）；索引 idx_dts_doctor / idx_sl_token。旧库须执行 011。**`share_links.add_count` / `nightly_briefings`（迁移 012，2026-08-17 分身分享+夜间简报一期 C）**：share_links 加 `add_count INTEGER NOT NULL DEFAULT 0`（分享链接被激活次数追踪，口径=被添加次数）；新建 `nightly_briefings` 表（id / representative_id FK users / specialist_id FK digital_specialists / briefing_date / content JSONB / status default 'ready' / created_at / updated_at；唯一键 uq_nb_rep_spec_date(representative_id, specialist_id, briefing_date)；索引 idx_nb_rep(representative_id)；模型在 `shared/models/nightly_briefing.py`）。旧库须执行 012。**`training_materials` / `exam_questions` / `exam_records`（迁移 013，2026-08-19 二期 F 合规培训考试，已并入 init_db.sql，模型在 `shared/models/training_exam.py`）**：培训材料（title / material_type regulation|rdpac|internal / content / version default '1.0' / status active|archived / created_by FK users；索引 idx_tm_type / idx_tm_status）、题库（material_id FK、question_type single|multiple|judge、options JSONB、answer JSONB、review_status pending|approved|rejected、review_reason/reviewed_by/reviewed_at、created_by；索引 idx_eq_status / idx_eq_material；**answer 永不向代表端返回**——`to_dict(expose_answer=False)` 默认不暴露）、考试记录（representative_id FK users、question_count / correct_count / score / passed / submitted_at；索引 idx_er_rep）。旧库须执行 013。**`digital_specialists` 加 is_official / representative_id（迁移 014，2026-08-19 二期 E 官方公共数字员工，已并入 init_db.sql，模型在 `shared/models/digital_specialist.py`）**：is_official BOOLEAN NOT NULL DEFAULT FALSE（官方公共数字员工标识）、representative_id BIGINT REFERENCES users(id)（个人分身归属代表；官方分身须为空）；索引 idx_ds_official。旧库须执行 014。**`academic_cards` / `card_push_records` / `notifications`（迁移 015，2026-08-19 二期 G 学术触达，已并入 init_db.sql，模型在 `shared/models/academic.py`）**：学术卡片（representative_id FK users、title VARCHAR(200)、content JSONB {conclusion,key_points[],summary,citations[]}、is_ai_generated bool default true、compliance_status passed/blocked、status active/archived；索引 idx_ac_rep）；卡片推送记录（representative_id/card_id/doctor_id 三 FK + **specialist_id FK digital_specialists（该医生订阅的代表分身，终审补充，卡片 useful 好评回流用）**、read_status unread/read/favorited/forwarded、read_at、tracked_seconds、feedback ≤500；UNIQUE(card_id,doctor_id) uq_push；索引 idx_cpr_doctor/idx_cpr_rep）；站内通知（user_id FK、type briefing_ready/card_feedback/card_question/card_new、title、content ≤1000、link、is_read bool default false；索引 idx_notif_user(user_id,is_read)）。旧库须执行 015。**`skill_packages` / `skill_audits` / `practice_sessions`（迁移 016，2026-08-19 二期 H AI陪练+Skill模版，已并入 init_db.sql，模型在 `shared/models/skill.py` / `shared/models/practice.py`）**：Skill 模版（name VARCHAR(100)、creator_id FK users、is_public bool default false、is_anonymous bool default false、audit_status pending/approved/rejected、audit_reason VARCHAR(500)、style_tags JSONB、heat INTEGER default 0、approval_rate DECIMAL(5,4)、**skill_weights JSONB——任何 API 不返回（`to_dict(expose_weights=False)` 默认不暴露）**；索引 idx_sp_public(is_public,audit_status)/idx_sp_tags(style_tags)）、Skill 审核（skill_id FK、auditor_id FK users、audit_result approved/rejected、reason；索引 idx_sa_skill）、陪练会话（representative_id FK users、skill_id FK skill_packages、scenario VARCHAR(100)、status in_progress/completed、scores JSONB {evidence_accuracy,objection_handling,communication_logic,overall}、turn_count；索引 idx_ps_rep）。旧库须执行 016。**`objection_scripts`（迁移 017，2026-08-20 二期 H 终审修复 3.2(5) 异议话术库，已并入 init_db.sql，模型在 `shared/models/practice.py` 的 `ObjectionScript`）**：scenario_type VARCHAR(50) NOT NULL、objection_content TEXT NOT NULL、response_guidance TEXT、version VARCHAR(20) default '1.0'、review_status pending/approved/rejected（default pending）、review_reason VARCHAR(500)、reviewed_by/created_by BIGINT；索引 idx_os_scenario(scenario_type)/idx_os_status(review_status)。旧库须执行 017。**`doctor_profiles` / `patient_edu_templates` / `edu_content_records`（迁移 018，2026-08-20 二期 I 医生端体验，已并入 init_db.sql，模型在 `shared/models/doctor_profile.py` / `shared/models/patient_edu.py`）**：医生偏好画像（doctor_id UNIQUE FK users、interest_areas JSONB、preferred_doc_type guideline|rct|real_world|case_report、preferred_style 简洁/标准/详尽、closed BOOLEAN default false 关闭个性化；索引 idx_dp_doctor）、患教模板（title VARCHAR(200)、disease_area 心血管|肿瘤|内分泌|呼吸|神经、content TEXT、version default '1.0'、review_status pending/approved/rejected default pending、review_reason VARCHAR(500)/reviewed_by/created_by；索引 idx_pet_disease/idx_pet_status）、患教内容记录（doctor_id FK users、template_id FK patient_edu_templates、content JSONB {title,body,notes,seek_care}、is_ai_generated BOOLEAN default true、visibility private/shared default private；索引 idx_ecr_doctor）。旧库须执行 018。**`skill_packages` 加 7 列 + `skill_off_shelves`（迁移 019，2026-08-20 三期 J Skill 生态闭环，已并入 init_db.sql，模型在 `shared/models/skill.py`）**：skill_packages 加 description VARCHAR(200)（治疗领域/一句话说明，元数据）、content TEXT（话术素材，仅审核人受控查看）、off_shelf_status VARCHAR(20) NOT NULL DEFAULT 'active'（active/off_shelved）、off_shelf_reason VARCHAR(500)、off_shelf_type VARCHAR(20)（compliance/author）、off_shelf_by BIGINT REFERENCES users(id)、off_shelf_at TIMESTAMP；索引 idx_sp_off(off_shelf_status)。新建 `skill_off_shelves` 下架记录存档（skill_id FK / operator_id FK / off_shelf_type VARCHAR(20) / reason VARCHAR(500) / created_at / updated_at；索引 idx_sos_skill）。旧库须执行 019。**`edu_content_records` 加 audit_status + 索引（迁移 020，2026-08-20 三期 M 患教专区审核流，已并入 init_db.sql）**：edu_content_records 加 `audit_status VARCHAR(20) NULL`（NULL=未分享 / pending=待审核 / approved / rejected；分享→pending、审核→approved/rejected、撤回→NULL）；索引 idx_ecr_audit(audit_status)。旧库须执行 020。连接通过 `shared/common/db_session.py` 的 `get_db` 依赖注入。常用 ORM 模式：

**审计表不可篡改（`scripts/migrations/002_audit_immutable.sql`）**：audit_logs 的 owner 是 NOLOGIN 占位角色 `medagent_audit_owner`；`medagent_audit`（审计服务专用，`AUDIT_DATABASE_URL` 配置）只有 INSERT/SELECT；`medagent` 只 SELECT。该 migration 还会把 medagent 从 superuser 降级（PostgreSQL 官方镜像默认把 `POSTGRES_USER` 设为 superuser，superuser 无视 REVOKE）。migration 只需执行一次（medagent 降级后无法重跑，补权限找表 owner 或单用户模式）。

```python
from shared.models.base import Base, TimestampMixin
class MyModel(Base, TimestampMixin):
    __tablename__ = "my_table"
    name = Column(String(100), nullable=False)
    tags = Column(JSONB)  # PostgreSQL JSONB
    status = Column(String(20), default="active")
```

## Compliance Rules

11 条规则（`shared/compliance-rules/rules.yaml`）：

| 规则 | 类型 | 动作 |
|------|------|------|
| R001 禁止承诺疗效 | keyword | **reject** |
| R002 禁止回扣暗示 | regex | **reject** |
| R003 禁止统方 | semantic (LLM) | **reject** |
| R004 禁止超适应症推广 | semantic | **reject** |
| R005 禁止贬低竞品 | semantic | **warn** (不拦截) |
| R006 禁止泄露患者信息 | semantic | **reject** |
| R007 禁止讨论未公开数据 | semantic | **warn** (不拦截) |
| R008 禁止附加销售条件利益输送 | regex | **reject** |
| R009 禁止馈赠财物 | keyword | **reject** |
| R010 禁止隐匿不良反应 | keyword | **reject** |
| R011 禁止误导用药 | semantic | **reject** |

完整 22 项清单映射矩阵见 docs/compliance-2026-22items-matrix.md（可拦截 → 规则；流程类 → 平台管控点）。

semantic 类规则依赖 `DASHSCOPE_API_KEY`（qwen-turbo），未配置时语义规则静默跳过。

**compliance 端点全集（2026-08-11 补记）：** `/check`（内部）、`/rules` + `/rules/reload` + `/rules/test`（admin/manager 管理，test 为规则试跑工具不入库）、`/redlines`（**净化版红线清单**——只含 rule_code/rule_name/rule_type/severity/action/description/enabled，绝不含 patterns/content，供 rep/移动端 HelpCenter 展示）、`/blocks` + `/blocks/{id}`（拦截记录）、`/blocks/stats?days=N&action=`（仪表盘热力图）、`/report/export`（3 Sheet 监管自查 xlsx）、`/stats`。2026-08-11 起除 /check /redlines 外全部 require_roles(*RULE_ADMIN_ROLES)。

**合规监控端点（2026-08-19 二期 E 补记，`app/api/monitor.py`）**：`/daily-summary?days=7`（拦截聚合日报：按天 × 规则 × action 聚合，风控看板数据源，**口径=action='reject' 拦截，warn/log 不计入**）、`/trends?days=30`（违规趋势：时间曲线 + 代表排名 top10 + 规则频率，同样只计 reject）。均 require_roles(admin/manager/compliance)，数据来自 compliance_blocks 同库直连 users。**待复核名单已移至 specialist-service**（`GET /api/v1/specialists/review-queue`，分身维度，见 Service Endpoints 章节）。

**fast 模式（2026-08-11 流式门禁引入）**：`POST /api/v1/compliance/check` 支持 `fast` 参数（透传给 `checker.check(fast=True)`）——**跳过 LLM 语义层，只跑关键词/正则**（毫秒级），fast 命中不写 compliance_blocks、不计 COMPLIANCE_BLOCKS 指标（阻断时由调用方对完整文本做 full 复核统一记录）。供 specialist 流式逐帧门禁使用。

**语义检查安全行为（S7）**：内容包裹在 `<user_content>` 标记中（其中的任何指令都只是数据）；LLM 输出**解析失败**（JSON 错误/截断）时按违规拦截（R999, action=reject）——这是注入攻击与截断的迹象；**网络/API 错误同样 fail-closed**（2026-08-12 B5 批起 R999 收敛，此前"网络错误 fail-open"的描述已过时）。

## Bailian WebSocket Protocol

数字专员问答通过百炼多模态交互 WebSocket 协议实现（`specialist-service/app/services/bailian_client.py`），非 HTTP：

1. Connect → `wss://dashscope.aliyuncs.com/api-ws/v1/inference`
2. Start message: `{task_group: "aigc", task: "multimodal-generation", model: "multimodal-dialog"}`
3. 收到 `DialogStateChanged` → 发送 `RequestToRespond`
4. 接收 `RespondingContent` 流 → 解析答案
5. Stop → 完成

降级：百炼不可用时走通义千问直调（`qwen_client.py`，OpenAI 兼容接口），300 字符限制，不含知识库检索。需要 `BAILIAN_API_KEY`（与 `DASHSCOPE_API_KEY` 不同）。

**空答案兜底（2026-08-06 实测修复，commit 908af39）**：百炼 App **未发布**/知识库无内容时 WS 协议全程正常（Listening → 回声 → RespondingContent）但 `RespondingContent.text` 为空——`chat()` 无异常返回空串。`AnswerGenerator.generate/generate_stream` 现在对空答案抛 `BailianException` 统一走 qwen 降级（此前会空回答 + 合规审核对空 content 报 400）。排查：`python scripts/probe_bailian_ws.py` 直连 dump 帧；App 发布后降级 warning 应消失。

**聊天 WS 流式链路（2026-08-06 三批实施后，REST `/chat` 保留为降级；2026-08-11 加逐帧合规门禁）**：
- specialist：`BailianClient.chat_stream()`（逐帧 yield delta/done）→ `AnswerGenerator.generate_stream()`（合规预检 → 流式 → 答案合规审核 → 审计 → done 帧，字段与 REST 返回一致 + type）→ WS 端点 `/ws/specialists/{id}/chat?token=JWT`（`app/api/chat_ws.py`：token 无效关 4401、专员不存在关 4404、question 空/超时/异常关 4500；`start → delta* → done` 帧，done 前 `_persist_conversation` 落库并带 conversation_id；send 统一加锁防 ConcurrencyError）。
- **逐帧合规门禁（2026-08-11）**：delta 帧路径每帧对累积文本做 fast 检查（关键词/正则，毫秒级），命中即停——**违规帧不转发**；随后对完整文本 full 复核（含语义层，写 chat_blocked 审计 + compliance_blocks），产出 `compliance` 帧（blocked + violations）+ 掩码 done（"该问题建议直接咨询医学顾问。"）。降级路径（Bailian 异常 → qwen）整段输出前同样过门禁。chat_ws 不转发 compliance 帧（RN 端 default case 忽略未知帧，onDone 处理 blocked），协议与前端零改动。
- gateway：`/api/v1/specialists/{id}/chat/ws` 双向透传代理（token 原样转发，网关不重复鉴权——WS scope 不经 BaseHTTPMiddleware）。
- mobile：`mobile/src/services/wsChat.ts` 走网关 8000（question 帧缓冲到 onopen 后发送）；`ChatScreen` 流式渲染增量气泡，8s 未收到 start 自动降级 REST（specialistAPI.sendMessage），blocked/violations 按 REST 同款拼装展示。

## Frontend — web/（Web 管理后台）

Vite 5 + React 18 + TypeScript + AntD 5 + @ant-design/pro-components + @ant-design/charts，纯 SPA。开发时 vite 把 `/api` 和 `/health` 代理到网关 `localhost:8000`（`vite.config.ts`，/health 是 M54 网关状态卡探活），生产由反代同路径转发。

13 模块 21 路由（懒加载，路由定义在 `web/src/App.tsx`，侧边菜单在 `web/src/constants/menu.tsx`；旧 `constants/routes.ts` 已删除）：仪表盘 `/dashboard`、数字专员 `/specialist/list`（新增/编辑在列表页 Modal 内）、分身监控 `/specialist/monitor`（2026-08-19 二期 E：分身状态监控与使用统计 + 冻结/解冻操作，`services/monitor.ts`）、拜访管理 `/visit/list`、知识库 `/knowledge/list`、合规规则 `/compliance/list` + 拦截记录 `/compliance/blocks`、合规风控 `/compliance/monitor`（2026-08-19 二期 E：聚合日报/趋势/待复核名单看板）、对话检索 `/compliance/conv-search`（2026-08-19 二期 E：对话日志全文检索）、审计查询 `/audit/list`、医生管理 `/doctor/list` + `/doctor/:id`、用户管理 `/user/list`、备案管理 `/filing/list`（2026-08-17 备案资质子系统：资质审核列表 + 审核抽屉）、医生认证 `/doctor-cert/list`（2026-08-17 医生端一期 B：医师认证审核列表 + 审核抽屉，`services/doctorCert.ts`）、合规培训 `/training/list`（2026-08-19 二期 F：培训材料管理 + 题库审核 + 考试记录，`services/training.ts`）、触达统计 `/compliance/card-stats`（2026-08-19 二期 G：学术内容触达统计看板，`services/cardStats.ts`）、Skill 管理 `/skill/list`（2026-08-19 二期 H：Skill 模版创建/审核受控查看权重，`services/skill.ts`）、患教模板 `/patient-edu/list`（2026-08-20 二期 I：患教模板库管理 + 审核，`services/patientEdu.ts`）、运营统计 `/doctor/stats`（2026-08-20 二期 I：医生活跃度 + 数字分身使用排行，`services/doctorStats.ts`）、系统配置 `/system/config`。另有登录页 `/login`。

API 约定：axios 实例 `web/src/services/client.ts`，`baseURL: '/api/v1'`；token 存 localStorage `medagent_token`，请求自动带 `Authorization: Bearer`。后端统一响应 `{code, message, data}`，分页接口的 data 是 `{items, total, page, page_size}`（见 `web/src/types/index.ts`）。非 401 的 4xx（含 403）由拦截器统一弹后端 message。

认证体系（2026-08-11 补记）：`context/AuthContext.tsx`（AuthProvider）持登录态，`pages/Login` 登录页，`components/RequireAuth.tsx` 路由守卫 + 401 跳登录，`services/auth.ts` 调 `/auth/login` + `/auth/me`；路由守卫只验登录态不验角色（M17 已知）。API 层按模块拆 `web/src/services/`（auth/audit/compliance/doctor/doctorCert/filing/knowledge/specialist/system/training/user/visit）。仪表盘另有 `components/LiveStatusStrip.tsx`（5s 轮询 live-status 迷你工位条，复用 `components/office/SpecialistCharacter.tsx` SVG 小人）。

**已知问题（2026-08-06 审计修复后，页面均已真实接线）**：
- 仪表盘：风险热力图（区域 × 近 7 天拦截量，数据来自 `GET /api/v1/compliance/blocks/stats`）、实时动态（审计日志 5s 轮询）、网关状态卡（真实探活 `/health`）
- 专员页：列表分页 + 创建/编辑/启停真实调用 + "数据"抽屉（stats）；知识库页：上传/审核/详情真实调用
- 系统配置页：只读展示配置状态（`GET /api/v1/system/config`，admin），配置经 .env 环境变量管理，不支持在线保存
- 新增端点：`/compliance/blocks/stats?days=N`（region join 失败自动降级 service 维度）、`/compliance/blocks/{id}`（完整内容+context）、`/system/config`（仅返回配置状态布尔，绝不返回密钥值）
- **医生管理缺口（2026-08-11 全文件审计确认）**：~~DoctorList「新增医生」按钮仅 message.info 占位~~（2026-08-11 已修 ModalForm 接线）；~~services/doctor.ts 的 AI 画像接口 GET /hcps/{id}/profile 已定义但无页面调用~~（2026-08-11 已修 DoctorDetail 画像卡片）；HealthDot.tsx 死代码（保留，可后续清理）；tsconfig.tsbuildinfo 残留（保留）

**数字员工办公室 3D 视图（2026-08-10 v4 完成 + 2026-08-11 视觉调优#2，已推 origin/master）**：专员列表页 `/specialist/list` Segmented 切换「办公室」视图 = 左侧 280px 出勤面板（AttendancePanel.tsx：环形出勤率/状态分布/今日对话/明细列表，与 3D 双向联动）+ 右侧 Three.js 3D 场景（**`three ^0.185.1` + `@types/three` 为唯一需老板拍板的额外依赖**，打破原零依赖约定；dependencies 常规项为 axios/dayjs/react-router-dom，注意 @types/three 在 dependencies 而非 devDependencies）。模块在 `web/src/components/office3d/`：
- `layout.ts` — 4×5=20 工位（COL_X 3.9 / ROW_Z 3.6，用户要求间距 1.5× 防拥挤；桌 2.08×1.17×0.96，人 1.3×）；`deskX/rowZ/sitPosOf/aislePosOf` 坐标函数
- `buildScene.ts` — CanvasTexture 深蓝网格地板 + 排间发光过道条
- `buildDesk.ts` — 白色工位（桌面 #f8fafc + 浅灰腿 + 浅蓝桌沿）+ 深色电脑；状态三色 emissive 脉动（working #1677ff 0.5↔1），offline 仅熄屏不变色
- `buildCharacter.ts` — 程序化白色人形（亮白主体 + 深炭四肢 #333），坐/站姿态插值 ≈0.4s（pose 0↔1）
- `simulation.ts` — 3s 轮询 `GET /api/v1/specialists/live-status` 数据驱动状态机：idle 过道巡逻 0.8u/s / working 走位 1.4u/s 到点坐下 / **offline 走回自己工位站立灰化**（target=sitPosOf(index)）；状态色 working #1677ff / idle #faad14 / offline #bfbfbf
- `labels.ts` — CSS2D 名牌（名字+状态色点+今日 N，y=2.0）
- `OfficeScene3D.tsx` — WebGL+CSS2DRenderer+rAF+raycast 选中操作卡（数据/编辑/停用·启用），相机 (0,13,12) / fov 45 / camTarget (0,0,0.5)

状态数据：后端 `live-status`（空时按 conversations 最近活跃推断，重启后 5 分钟降级窗口粗粒度报 working）。验证门 `cd web && npm run build`；E2E 在 `t10-office3d/e2e_v4.py`（**投影断言 project() 硬编码相机/布局常量，改相机或 layout.ts 必须同步改该脚本**）。

## Frontend — mobile/（React Native 移动端）

React Native 0.75 + TypeScript + react-navigation，原生工程已齐（2026-08-06 bring-up 完成，Pixel_7 模拟器全链路实测通过）。包名/bundle ID `com.medagent.mobile`，App 显示名 `MedAgent`，入口 `mobile/index.js` → `src/App.tsx`（app.json name 与 MainActivity/AppDelegate moduleName 必须一致，否则首启红屏）。

```bash
# 构建/运行（JDK 17 + ANDROID_HOME=D:\AndroidSDK + AVD Pixel_7 已就绪）
cd mobile/android && ./gradlew assembleDebug          # 出 app-debug.apk
"D:/AndroidSDK/emulator/emulator.exe" -avd Pixel_7 &  # 起模拟器
cd mobile && npx react-native start                   # Metro（Node v25 实测可用）
# git-bash 下 npx react-native run-android 调 gradlew.bat 会失败（'gradlew.bat' 不是内部或外部命令）→ 手动装：
cd mobile/android && ./gradlew.bat app:installDebug -PreactNativeDevServerPort=8081
adb shell am start -n com.medagent.mobile/.MainActivity
# 测试：cd mobile && npx jest（96 用例，12 套件：api-contract + qualification-contract（备案资质契约）+ share-contract（分身分享契约）+ briefing-contract（夜间简报契约）+ exam-contract（培训考试契约）+ academic-contract（学术触达契约）+ practice-contract（AI陪练/广场/分身管理/Skill 发布·我的 Skill 契约）+ wsChat + asr + tts + asrStreaming + date，锁 URL/method/body/响应形状；2026-08-20 三期 J 核对）
```

结构：`mobile/src/navigation/AppNavigator.tsx`（Stack：登录 → 底部 4 Tab：工作台/对话/医生/我的 → 拜访/医生详情等子页）+ `navigation/types.ts`（导航参数类型；2026-08-13 确认旧记录的死路由 `HCPProfile`/`ComplianceRuleDetail` 已不存在，仅残留 HCPProfile 类型接口）；`mobile/src/api/` 按服务拆分（academic/auth/compliance/content/exam/hcp/practice/specialist/visit 9 文件；practice.ts 含 practice/plaza/twin 三组 API，2026-08-19 二期 H），统一走 `mobile/src/api/client.ts`：Android 模拟器 `http://10.0.2.2:8000`、iOS `localhost:8000`（都是网关）；登录态在 `mobile/src/store/AuthContext.tsx`（AsyncStorage 存 token，仅 401 才登出，网络抖动保留登录态）。**契约铁律：请求体/响应形状以 src/api/*.ts 为唯一映射点**（snake_case、分页解包都在这里做，不污染屏幕组件）；改动后端响应形状或端点后，先改 api 层 + 契约测试，再动屏幕。

其他模块（2026-08-11 全文件审计补记）：`src/components/` 六组件（Icon/EmptyState/EvidenceBadge/FAB/ProgressRing/VisitCard）、`src/constants/theme.ts`（设计令牌）、`src/utils/date.ts`（`formatLocalDate` 本地日期语义 + 4 测试）、`src/services/recorder.ts`（录音封装，`declare const atob` 绕 tsconfig 无 DOM lib）、`jest.setup.js`（mock AsyncStorage）。屏幕 32 个：Tab 4（Home/Specialists/HCPs——组件名 `HCPSearchScreen`/Profile）+ 子页 28（Chat/HCPDetail/VisitPrepare/VisitInProgress/VisitEnd/Content/ContentDetail/ComplianceManual/ComplianceCenter（个人合规中心 `ComplianceCenterScreen.tsx`，备案状态/到期提醒/资质上传提交，2026-08-17 备案资质子系统；2026-08-19 二期 F 扩展培训材料/在线考试/承诺书签署入口）/Settings/NotificationSettings/HelpCenter/VisitDetail/Login/Share（分身分享 `ShareScreen.tsx`）/BriefingList（夜间简报列表 `BriefingListScreen.tsx`）/BriefingDetail（简报详情 `BriefingDetailScreen.tsx`）/TrainingMaterial（培训材料 `TrainingMaterialScreen.tsx`）/Exam（在线考试 `ExamScreen.tsx`）/Commitment（承诺书签署 `CommitmentScreen.tsx`，2026-08-19 二期 F）/CardList（学术卡片列表 `CardListScreen.tsx`，2026-08-19 二期 G）/CardCreate（学术卡片生成 `CardCreateScreen.tsx`，2026-08-19 二期 G）/PracticeList（AI 陪练场景选择+历史 `Practice/PracticeListScreen.tsx`，2026-08-19 二期 H）/PracticeChat（AI 陪练多轮对话+评分 `Practice/PracticeChatScreen.tsx`，2026-08-19 二期 H）/Plaza（Skill 广场 `Plaza/PlazaScreen.tsx`，2026-08-19 二期 H）/TwinManage（分身管理 `Twin/TwinManageScreen.tsx`，2026-08-19 二期 H）/SkillRelease（Skill 发布 `Skill/SkillReleaseScreen.tsx`，2026-08-20 三期 J）/MySkillList（我的 Skill `Skill/MySkillListScreen.tsx`，2026-08-20 三期 J））。Profile 入口：「分身分享」→ Share、「夜间简报」→ BriefingList（2026-08-17 一期 C）+「AI 陪练 / Skill 广场 / 分身管理」三入口（2026-08-19 二期 H）+「Skill 发布 / 我的 Skill」两入口（2026-08-20 三期 J）。**Android Kotlin 目录是非标准布局**：`android/app/src/main/java/com/com.medagent.mobile/`（com 下直接套一个名为 `com.medagent.mobile` 的目录，非常规三段式）——Kotlin 不强制目录与包名一致，构建不受影响，但别按标准布局"整理"它。

**已知问题（2026-08-06 第四批后）**：
- 录音链路已接但 NLS_APPKEY 未配：`VisitInProgressScreen` 录音 → PCM 分片推 ASR WS，服务端未配置时发 error 帧 fail-closed（前端提示"NLS 识别通道未配置"，不产生假文本）；`ChatScreen` 语音按钮为入口提示 Alert（语音转写需在拜访中页使用——无拜访上下文），拜访中页为全链路流式语音输入。2026-08-12 真机联调已实测（Android 13+ 麦克风运行时权限 / message_id UUID / 流式三守卫等修复见 Known Gaps 已修批）；M19 已修复——轮询增量流式推流（录音中每 2s 读增量推送，stop 推完剩余并发 stop 帧）。
- 说话人标签已渲染（ASR 帧 speaker 字段，rep/doctor，缺省 rep）；服务端 NLS 分离参数名（enable_speaker_identity/speaker_diarization）待真机确认。
- 聊天 WS 流式已接（走网关 8000），未配真实百炼 key 时未做模拟器端到端冒烟。
- HelpCenter 已接合规规则接口（红线清单真实数据，reject 类规则）；联系方式仍为静态占位。
- iOS 未实际构建验证（本机无 Xcode；moduleName 已对齐，首次构建需实测）。

## Frontend — mobile-doctor/（React Native 医生端，2026-08-17 一期 B）

React Native 0.75 + TypeScript + react-navigation，独立工程（骨架自 mobile/ 移植，包名/bundle ID `com.medagent.doctor`，App 显示名 `MedAgent·医生端`，入口 `index.js` → `src/App.tsx`）。功能：医生手机号/密码登录（复用 auth 链路，role=doctor）、医师资格认证上传（DocumentPicker + multipart → auth `/api/v1/doctors/certs`，审核状态回显）、医学 AI 问答（REST `/api/v1/medical/qa`，强制渲染免责声明与"AI 生成"标识）、分身订阅与激活（`/api/v1/share-links/{token}/activate` + `/api/v1/twin-subscriptions`；知情同意弹窗文案对齐需求 5.3(5)；对话 REST 无流式）、学术卡片收件箱与反馈（`/api/v1/card-pushes`：收件箱/阅读追踪/反馈 + `/api/v1/card-pushes/notifications` 站内通知，2026-08-19 二期 G）、医生端体验四屏（2026-08-20 二期 I：偏好设置 `/api/v1/doctor-profiles` 学习/修改/关闭个性化 + 官方广场 `/api/v1/doctor-plaza` 浏览/添加（知情同意）+ 患教卡片 `/api/v1/patient-edu` 选模板生成（默认仅本人可见）+ 分享到专区/撤回 + 患教专区浏览（`/api/v1/patient-edu/zone`，2026-08-20 三期 M）+ 收藏历史复用 `/api/v1/favorites`）、深链 `medagent-doctor://twin/:token` → 激活页（AndroidManifest scheme 已注册 + AppNavigator linking；iOS 未验证挂账）。

```bash
cd mobile-doctor && npx tsc --noEmit                 # 零错误
cd mobile-doctor && npx jest                         # 18 契约用例（doctor-contract + inbox-contract + doctor-exp-contract：偏好/广场/患教（含分享到专区/撤回/专区浏览）/收藏历史契约，2026-08-20 三期 M）
cd mobile-doctor/android && ./gradlew assembleDebug  # BUILD SUCCESSFUL（JDK 17 + ANDROID_HOME 同 mobile）
```

结构：`src/navigation/AppNavigator.tsx`（linking 深链 + Stack：Login → MainTabs[MedicalQA/MyTwins/Profile] → TwinActivate/TwinChat/CertUpload → Inbox/CardDetail（2026-08-19 二期 G 学术卡片收件箱/详情反馈）→ Plaza/Preference/PatientEdu/Favorites（2026-08-20 二期 I 官方广场/偏好/患教/收藏历史）；未登录时深链落到 Login）、`navigation/types.ts`（TwinActivate 参数 `{ token?: string }`——深链参数为 string）、`src/api/`（client.ts 自 mobile 原样拷贝，`medagent_token` 存储键一致；auth/doctor/medical/twin/inbox/doctorExp/favorites 七文件，契约以 api/*.ts 为唯一映射点）、`src/store/AuthContext.tsx`（useAuth：user/login/logout）、`src/constants/theme.ts` + `src/components/Icon.tsx` 自 mobile 拷贝。新增依赖仅 react-native-document-picker（上传）。细节：MyTwins 屏蔽态置灰禁聊；TwinActivate 对 activate 返回 subscribed=true 且 subscription_status=blocked 时不跳转（Alert「该分身已被暂停」，2026-08-17 B9 修复）；Profile 显示登录用户信息（useAuth）+ 医师资格认证入口（→ CertUpload，副标题回显审核状态）+ 退出登录。

## Real-time ASR（实时转写）

> 配齐 NLS/百炼 key 后的真机联调步骤、待确认点与排障手册见 `docs/real-device-runbook.md`（真机需改 `mobile/src/config.ts` 的 `DEV_HOST` 为宿主机局域网 IP，见 runbook 2.4）。第 3 节后端冒烟基线已于 2026-08-06 实测回写（一键复跑：`python scripts/smoke_runbook.py`）。

实时转写链路已改用**阿里云实时语音识别**（听悟是离线批处理+3s 轮询，达不到方案的 <2s）：

- 服务端：`visit-service/app/services/realtime_asr.py`（`RealtimeAsrClient`：AK/SK 签名换 NLS 临时 Token → `wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1?token=` → StartTranscription → 二进制 PCM 推流 → SentenceBegin/ResultChanged/SentenceEnd 事件；`enable_intermediate_result=true` 实时出字）。未配置 `NLS_APPKEY` 自动降级 `MockRealtimeAsrClient`（模拟文本，可联调）。
- WS 端点：`/ws/visits/{visit_id}/asr?token=<JWT>`（移动端推 PCM → 增量 JSON 回推 → 断句落库 conversation_transcript → 每句实时合规检查并回推 compliance 事件）。**注意 WS 不走网关**（网关 proxy 不支持升级），直连 visit-service:8002。
- 听悟客户端保留用于拜访后归档（完整音频离线转写）。
- 移动端接入点（已接，2026-08-06；M19 流式化 2026-08-11）：`react-native-audio-record` 录 WAV(16k/16bit/mono) → **流式推流**（M19 修复——录音期间每 2s 轮询读增量推送：Android 录音中读 `temp.pcm` 裸增量，iOS 读 WAV 增量；stop 后统一切 WAV，不再"录完再推"）→ 16KB 分片经 `mobile/src/services/asr.ts`（`connectAsrStreaming`）推 WS；`{"type":"stop"}` 结束；sentence 帧增量回填输入区，completed 帧回传末句全文走 `addTranscript` 落库。NLS_APPKEY 未配时服务端 fail-closed（error 帧 + 关 4500，不落假文本）。

## Known Gaps（后端已知缺口，勿误以为已实现）

已修（2026-08-04）：~~audit 零鉴权~~（S2）、~~"不可篡改"未生效~~（S3）、~~visit PUT 越权~~（S4）、~~零 RBAC~~（S6）、~~规则改动/审核不入审计~~、~~语义合规提示注入~~（S7）、~~prod 暴露公网~~（S8）、~~网关中间件顺序/预检 401~~（H10）、~~Excel 导出经网关 500~~（H11）、~~visit→specialist 401 永久 degraded~~（透传用户 JWT）、~~Web 仪表盘假数据~~、~~用户管理 404~~（`/api/v1/users`）、~~知识库 approve 反转~~、~~compliance_blocks 无写入方~~（check 端点拦截即入库，实测 R003 落表）、~~实时转写路线错误~~（服务端已切阿里云实时 ASR 流式链路 + WS 端点，实测 Mock 全链路；移动端录音待原生工程）。

已修（2026-08-05~06）：~~citations 恒空~~（百炼 extra_info.docs 解析引用溯源）、~~feedback/favorite 是桩~~（conversation_feedback/favorites 真落库，实测点赞 2 行 + 收藏 1 行含问答快照）、~~规则热更新只读 YAML~~（DB 规则加载，DB 覆盖 YAML + TTL 60s 重载）、~~移动端无法构建~~（RN 0.75.0 原生工程 + api 契约修复 7 处 + 契约测试 11 用例 + Pixel_7 实测全链路）、~~chat 无 conversation_id~~（前端反馈/收藏拿不到主键）、~~mobile 三处响应形状错位~~（specialist 纯数组、compliance 分页对象+字段名、favorite 必填 body 422）。

已修（2026-08-06 三批实施，23 提交本地未 push）：~~web 无登录页~~（AuthProvider + 登录页 + 路由守卫 + 401 跳转）、~~mobile 五屏零后端调用~~（VisitDetail/Profile/Settings 接真实接口、NotificationSettings AsyncStorage 持久化；HelpCenter 除外）、~~ContentScreen MOCK_CONTENT~~（接 knowledge API + 新增文档详情页）、~~移动端无录音/无 WS 客户端~~（录音库 + 权限 + asr.ts/wsChat.ts + 拜访页录音转写接线 + 聊天流式）、~~短信通道仅 ConsoleSender~~（AliyunSmsSender dysmsapi 真实现，缺配置 fail-fast，4 测试全 mock）、~~聊天一次性返回~~（specialist WS 端点 + 网关 WS 代理 + mobile 流式渲染 + 8s 降级 REST，question 帧缓冲到 onopen 发送）。

已修（2026-08-06 全仓审计三批修复，21 提交本地未 push，详见 docs/audit-report-2026-08-06.md）：
- ~~移动端拜访全流程断裂~~（start visit_id 契约/end 双调/假摘要删除/transcript 键位/WS 合规接线/VisitRecord 全字段映射）
- ~~分页契约错位~~（paginate 顶层 total/page/page_size 加法兼容）
- ~~互动历史两端必崩~~（hcp 返回裸数组 + 两端映射）；~~AI 画像/医生详情字段错位~~（mobile hcp 映射 + web 字段修复 + Android 标签弹窗）
- ~~会话历史 IDOR~~（归属校验三处）；~~compliance LLM 异常 fail-open~~（R999 收敛）；~~auth 审计客户端缺 before_value 致 PUT /users 500~~
- ~~INTERNAL_API_KEY 模板值绕过~~、~~网关 JWT_SECRET 默认回退~~（fail-fast）；~~manager 自授 admin~~（仅 admin 改角色 + 禁自改 + users 重读库）；~~验证码 off-by-one/枚举泄露~~；~~pre-visit 跨用户泄露~~；~~审计查询/导出无角色限制~~
- ~~knowledge/search 双向不可达~~（移出 INTERNAL_PATHS）；~~web 六页假动作~~（专员/合规/审计/用户/知识库/系统配置全部真实接线）；~~合规规则字段无校验~~；~~specialist 列表恒空/stats 双倍~~；~~gateway 限流 user_id 死代码/统一错误格式/WS 关闭码/health 假聚合~~
- ~~knowledge 审核流卡死/上传无校验/未上架泄露/ES 从未写入~~（ES 索引接线、驳回清索引、白名单+50MB、角色可见性）
- ~~dev/prod compose 审计写入失效~~（AUDIT_DATABASE_URL + :? 强校验）、~~deploy.yml 分支永不触发~~、~~e2e/debug 脚本过时~~、~~requirements.txt.tmp 残留~~

已修（2026-08-06 真机联调冒烟，commit 908af39/b7d2183）：
- ~~百炼空答案绕过降级~~（App 未发布时 RespondingContent.text 空 → 空回答 + 合规 400；现抛 BailianException 走 qwen 降级）
- 冒烟基线已建立（`scripts/smoke_runbook.py` 可一键复跑）：8 服务健康 / DEV_MODE 验证码登录 / 专员分页契约 / R001·R003 真实命中 / 审计 request_id 贯穿 —— 全部通过

已修（2026-08-11 四合规/安全债，commit e6c0d75..b63f736，已推 origin/master）：
- ~~require_roles 只信 token~~（降级/停用后旧 token 最长 7 天仍可访问受限端点 → 每次受限请求查库，role/status 以库为准，403 统一 PermissionError 渲染 {code,message,data}）
- ~~流式答案合规旁路~~（generate_stream 事后检查时违规文本已发出 → delta 逐帧 fast 门禁：跳语义层只跑关键词/正则，命中停发 + full 复核写审计/拦截记录 + compliance 帧 + 掩码 done；降级路径同门禁）
- ~~hcp mass assignment~~（create/update 白名单外字段 400 + repo _filter_writable 兜底，id/created_at/updated_at 不可覆盖，批量导入不受影响）
- ~~收藏多轮错配~~（toggle_favorite 以被收藏行为锚点取同轮问答，过滤 id<=锚点防快照到后续轮次）
- 配套测试：compliance TestFastMode、specialist 中流阻断/降级阻断、hcp repo+API 白名单、收藏 3 个多轮场景；8 服务回归全绿（audit 13/auth 44/compliance 43/specialist 70/hcp 27/visit 53/knowledge 44/gateway 26）（此为 2026-08-11 首批提交时的快照）

已修（2026-08-11 十项缺陷 + 向量链路根因，commit 012ab1a..2d0db2b + 6dce273，已推 origin/master；2026-08-11 全文件审计补记）：
- ~~十项缺陷 #1-#9~~：compliance /rules·/blocks·/stats 收紧 require_roles(*RULE_ADMIN_ROLES) + 新增净化版 `/redlines`（rep/移动端红线清单，无 patterns/content，mobile compliance.ts 已切换）；hcp /{id}/interactions 角色感知（rep 强制 user_id 过滤）；audit `logger.log()` 加 `**kwargs` 吸收未知键（原请求体未知键 → 500 审计静默丢失）；chat_ws 先 accept 再 close 4401/4404（旧实现 close 被握手 403 吞掉落 4500）；web 时间 3+1 处 UTC 解析；knowledge /feedback doc_id str() 强转；web UserList 编辑按角色（manager 不带 role / admin 禁自改）；mobile content.ts doc_type→type 映射（Tab 过滤恒空）；smoke_runbook 强制 SMOKE_PHONE + 冷却响应 data:null 防护
- ~~网关 WS 代理 websockets 15.x 适配~~（send_text/receive_text 在 15.x 改名 send/recv，AttributeError 被吞 → WS 流式转发实际一直坏的；_upstream_send/_upstream_recv 兼容适配，实机走网关 4401 + start→delta→done 全链路通过）
- ~~听悟 _parse_result 恒空~~（按真实 GetTaskInfo 结构解析 result.text/result.sentences，speaker_id=0 用 is not None；另驳回写审计、归档清索引、登录失败写审计一并补上）
- ~~**向量化链路从未真正生效**~~（EMBEDDING_DIM=1536 是错误假设，text-embedding-v3 最大 1024 维 → collection 以 1536 建库，每次 upsert 维度不匹配**静默失败**（DashVector 响应式 API 不抛异常 + 代码不查返回码），文档全部"上架成功但向量缺失"；已修 EMBEDDING_DIM=1024 + upsert/create 响应码检查（失败 raise）+ **删除重建 collection**；delete_doc 双 bug——Collection.delete 不支持 filter + filter 字符串必须双引号，改先 query(filter) 再 delete(ids=)）
- ~~网关 knowledge 路由超时 30s→120s~~（百炼导入 ~28s + 向量化，30s 网关先断 → "业务完成但客户端 504"）
- 测试基线（2026-08-11 快照）：audit 19 / auth 50 / compliance 59 / gateway 38 / hcp 36 / knowledge 51 / specialist 71 / visit 61 = **385 passed**；mobile jest 70；web build PASS

已修（2026-08-11 第二批：web 医生管理 + 移动端语音链路，用户逐项拍板后实施）：
- ~~web 新增医生占位 / AI 画像未展示~~（ModalForm 真实接线 POST /hcps；DoctorDetail 画像卡片含降级兼容；画像映射移植 mobile hcp.ts）
- ~~移动端语音输入 stub~~（真实链路已接：录音 → PCM → visit-service WS → NLS；M19 修复：录完突发推流改轮询增量流式推流，服务端 asr_ws.py 零改动）
- ~~听悟 TTS 未接~~（新端点 GET /api/v1/nls/tts-token 下发 {token, appkey, expires_at}，复用 realtime_asr.get_nls_token；mobile tts.ts 直调 NLS REST 合成 + react-native-sound 播放；未配 NLS_APPKEY 时 4xxx 报错、按钮禁用提示）
- ~~关键节点标记/话术建议实时推荐（后续版本）~~（visit-service process_transcript 节流 20s + ≥6 字触发 qwen-plus 生成 {key_nodes, suggestion}，失败降级不阻塞；落库 visit_records.key_nodes（迁移 006）；transcript 响应新增 key_nodes/ai_suggestion；mobile 拜访中「AI 实时推荐」区展示 + 话术朗读）
- ~~NLS_APPKEY 未配~~（.env 配置位就绪；NLS_MOCK=1 联调）
- ~~百炼 App 未发布 → 对话恒降级 qwen~~（用户确认已发布，降级解决）
- mobile host 集中：src/config.ts（API/ASR/聊天 WS 三处，真机改一处）

已修（2026-08-12 真机联调批，commit ff2db8d..6290e1f，已推 origin/master）：
- ~~end_visit 经专员链路中转~~（百炼 App 输出是聊天式散文，发布与否都满足不了 end_visit 的 JSON 契约，旧流程白付专员 ~8.4s + 二次生成 ~3.1s → 直调 qwen-max JSON prompt 一次生成 ~3-9s；**时间墙 = qwen-max 生成延迟**，qwen-flash ~2.4s 可把 `visit_manager.py` 的 `model="qwen-max"` 换名一键切换）
- ~~end_visit 空转写写出空总结/合规 400~~（qwen 返回合法 JSON 但 summary 为空（空转写偶发）→ 视为不可用写占位串可重试；无转写内容直接占位串不发 AI 调用；转写合规预检与 qwen 生成**并发**执行；画像更新 fire-and-forget 不阻塞主流程）
- ~~end_visit 请求体必填~~（移动端不带 body 422 弹"请求失败" → 改可选，接口签名兼容）
- ~~hcp /profile 同步 LLM 占死事件循环~~（画像生成 8s 期间同网关 /hcps/{id}、/interactions 全部排队 7.7s → asyncio.to_thread 线程池；test_profile_event_loop.py 回归）
- ~~specialist 空内容帧白等~~（App 未发布时空内容帧 150ms/帧 × 60 帧上限白等 ~9.2s → 连续 8 帧空文本提前降级 qwen ~1.2s；test_bailian_empty_fallback.py）
- ~~NLS message_id 非 UUID~~（真实联调发现 task_id-N 被网关 40000002 MESSAGE_INVALID 拒绝 → 32 位 hex UUID）
- ~~Android 录音静默失败~~（Android 13+ 麦克风运行时权限请求）+ ~~异议列表 key 冲突~~（全局唯一 key）
- ~~录音双按双会话泄漏~~（press 入口同步防重入）；~~TTS 合成无超时~~（30s 超时 + 播放初始化错误透传底层信息）；~~asr 流式推流三处竞态~~（轮询重入门禁 / 空块自旋终止 / flush 串行链）
- 测试基线（2026-08-12 全量修复批后）：audit 19 / auth 50 / compliance 59 / gateway 40 / hcp 38 / knowledge 51 / specialist 74 / visit 73 = **404 passed**；mobile jest 70（6 套件）；web build PASS

已修（2026-08-13 全项目审查修复批，9 域并行审查 320 文件 + 11 域并行修复，7 高 23 中全修）：
- ~~web manager 编辑用户必 403~~（UserList 仅手机号变化才带 phone + 非 admin 禁编辑手机号）；~~compliance 禁用 YAML 源规则无效~~（_load_db_rules 加载全量行、DB disabled 覆盖 YAML、单点过滤；update_rule content 非 dict 400 防毒化 DB 规则加载）
- ~~mobile 今日拜访恒空~~（date_to 传 T23:59:59）；~~聊天违规明细恒空~~（matched_text/reason 兜底）；~~AI 占位串误判 completed~~（识别占位串 retryable + VisitEnd 重试）；~~start_visit 静默丢字段~~（不发送 + UI 注明仅本次参考）
- ~~备份 OSS 30 天清理正则死~~（\d{6}）；~~init_db.sql 缺 006/008 列~~（visit_records 补 key_nodes/status，旧库仍跑 006/008）；~~restore 生产建库必挂~~（--pg-user + PG_ROOT_PASSWORD）；~~load_config .env 非空默认键覆盖失效~~；~~smoke 断言恒绿~~（blocked/violations 真断言 + 非零退出）；~~docker-verify 漏 auth~~；~~ci-pipeline 非法 Flow YAML~~（按官方语法重写，lint 不再 || true，测试覆盖 8 服务+shared+web+mobile）
- ~~visit qwen 无超时~~（60s/重试 1）；~~_llm_recommend 行锁跨 LLM~~（冷却无锁读、LLM 锁外、短持锁追加+populate_existing 真重读）；~~WS 丢 warn 违规~~（violations 非空即推帧+落库）；~~异议语义层畸形输出 500~~（形状校验坏项跳过）；~~末句 REST 双写~~（尾缀去重 duplicate:true）
- ~~specialist 流式门禁重复拼接~~（accumulated=帧全量）；~~流式传输异常绕过降级~~（chat_stream 统一转 BailianException）；~~降级同步调 qwen~~（to_thread+30s 超时）；~~/feedback 跨用户~~（require_roles admin/manager）
- ~~验证码并发复用~~（Lua consume-if-match：计数+比较+DEL 单脚本原子）；~~hcp 画像 qwen 无超时~~（30s）；~~网关 XFF 失真~~（TRUSTED_PROXY_CIDRS 信任代理才保留注入头，默认行为不变）；~~knowledge 索引先于终态写入~~（先 _finish_approve 后写索引）；~~knowledge 检索阻塞事件循环~~（to_thread）；~~prod compose env_file 指向不存在路径~~（../.env + 运行命令注释）；~~arms-monitor 告警死配置~~（PromQL+完整参数+List 后 Update 幂等）
- 测试基线（2026-08-13 修复批后）：audit 19 / auth 56 / compliance 64 / gateway 46 / hcp 39 / knowledge 57 / specialist 85 / visit 87 = **459 passed**；mobile jest 73；web build PASS

已修（2026-08-13 低危批，8 域约 53 项，11abedb..d9cfa9e 已推 origin/master；fable 终审 1 中 6 低，中危与 1 项低危已修、其余挂账见下）：
- shared：~~HTTPException/422 形状不统一~~（S1 统一渲染，见 Shared Layer 节）；~~.env.example 缺 CORS_ALLOW_ORIGINS~~；~~NLS_APPKEY truthy 占位绕过 fail-closed~~（改空串）；~~默认口令守卫子串误判~~（make_url 精确比较）；~~prod postgres max_connections 默认 100 不够~~（300）；~~e2e 对已收紧 RBAC 端点断言 200~~（改 401）
- auth/audit：~~密码登录时序枚举~~（dummy bcrypt 拉平）；~~重复手机号/坏 manager_id 500~~（预检 + IntegrityError 兜底）；~~非 dict body 500~~；~~审计时间非法 500~~；~~保留天数 0 删光审计~~（守卫）；~~审计列超长静默丢~~（按列长截断 + request_id 用上下文值）；~~SMS 阻塞/每次重建 sender~~（to_thread + 缓存）；~~并发发码覆盖~~（SET NX）；未知号时序补偿（缓解）
- visit：~~WS 兜底落库无状态复查~~；~~end_visit 重试 violations 翻倍~~（去重）；~~status 非法值静默~~（白名单）；~~已封存拜访可开 ASR~~（连接即拒，不建付费会话）；~~finish 固定 0.5s 丢末句~~（等 TranscriptionCompleted）；~~full_transcript 无类型校验~~
- knowledge/compliance：~~/check 非字符串 500 + "false" 被当 true~~；~~review 缺键默认驳回~~；~~上传字段无长度校验~~；~~DV query 不查响应码静默空结果~~；~~test_embed 断言 1536~~；~~/check 无长度上限~~；~~test_rule 把 R999 显示为未命中~~（inconclusive 标记）
- specialist：~~COMPLIANCE_BLOCKS 恒 0~~（阻断落点接线）+ chat_stream 死代码删；~~CRUD 校验缺口~~；~~问题被拦不写审计~~（question_blocked）；~~收藏并发 500~~（IntegrityError 幂等）；~~300 字限制未落实 + 降级无多轮上下文~~（截断 + 最近 3 轮注入）
- hcp/gateway：~~WS 上游仍带 token query~~（首帧 token 不再拼）；~~上游 JSON 解析失败 500 纯文本~~（502 code 5005）；~~hcp 404/422 形状不统一~~（缺档案 422 code 4001，对齐 knowledge 约定；注意此前是 404）；~~非 dict body 500~~；~~画像缓存 scan 前缀过宽~~；~~医生档案写操作零审计~~（create/update/tags/import 留痕）
- web：~~状态搜索未传参~~；~~audit keyword 无搜索列~~（已加）；~~14 处双弹 toast~~；~~兜底文案"无权限操作"误导~~（改"请求失败"）；~~routes.ts 死代码~~（删除）；~~网络错误无提示~~（拦截器补兜底，终审发现）
- mobile：~~"我的统计"误路由~~（移除）；~~Content 缺资讯 Tab~~；~~api 层 3 处死代码~~（删除）；~~Home/HCP 失败静默置空~~（错误态+重试）；~~结束按钮未含 sending~~；~~历史 evidence_level 恒空~~（移除字段）
- 测试基线（2026-08-13 低危批后）：audit 26 / auth 70 / compliance 72 / gateway 49 / hcp 54 / knowledge 64 / specialist 103 / visit 99 = **537 passed**（+shared 19）；mobile jest 73；web build PASS
- **低危批挂账**（终审记录，下轮候选）：send-code 撞 SET NX 的 4002 文案宣称"已发送"与实际不符；B2 去重对 matched_text=None 条目过宽；B5 时序测试断言边界偏紧（CI 高负载或 flaky）；"资源不存在"语义码 4000（HTTP 404）与 4001（HTTP 422）全仓并存待统一；E7 审计调用同步等待 5s 可考虑 create_task 异步化
- 已修（2026-08-12 全量修复批，B1-B7，本地未提交）：~~拜访无显式取消~~（POST /visits/{id}/cancel + visit_records.status 列，迁移 008 待实跑）、~~end_visit 重复结束报错~~（行锁 + 移动端 getById fallback）、~~follow_up 依赖专员链路常 degraded~~（直调 qwen）、~~模拟输入注入假转写~~（删 simulateInput 改真实文本输入）、~~拜访任务/收藏无移动端页面~~（TaskList/Favorites 新页 + Profile 真实计数）、~~web 无拜访管理页~~（VisitList + 任务展示）、~~专员数据抽屉无反馈明细~~（新接口 GET /specialists/{id}/feedback）、~~manager 可改他人手机号接管账号~~（仅 admin）、~~合规检查 fail-open~~（两处 client 抛异常 + 语义层网络错误 R999 拦截）、~~验证码并发可重放~~（Redis Lua 原子消耗）、~~生产可用 console 短信打印验证码~~（非 dev 禁 console 通道）、~~网关 CORS 全放行~~（env 白名单）、~~网关 WS 零鉴权 + token 明文 query~~（网关验 token + 首帧 auth 帧协议，保留 query 兜底）、~~XFF 伪造透传~~（网关覆盖为真实对端）、~~默认 DB 密码生产可用~~（shared/db_session 启动守卫）、~~审计 keyword 参数被忽略~~（ILIKE 多字段搜索）、~~HCP 标签仅 admin/manager~~（放开任意登录用户）、~~live-status 泄露他人问题内容~~（非 admin 剥离 snippet）、~~ES 检索含未上架文档~~（status=ready 过滤）、~~knowledge search product_id 非 int 500~~（显式校验）、~~备份静默回退默认密码~~（DB_USER/DB_PASSWORD + fail-fast + 秒级时间戳）、~~pg_restore 部分失败假成功~~（--exit-on-error）、~~docker-verify 构建失败被 tail 掩盖~~（pipefail）、~~通知页 4 个死开关~~（改"即将上线"）

**仍为假数据/未实现（勿误以为已做，2026-08-06 第四批后更新）**：
- 需求级缺口（用户暂缓）：飞书导入/双向同步、知识库内容库（`knowledge-base/` 空目录，方案要求 100-300 篇文献）、ES 真实实例（ES_URL 配置才启用，索引接线已做；ES_URL 未进 .env.example）、表格/图片 OCR 自动解析（依赖百炼云）、web 检索测试页
- ~~web 医生管理：DoctorList「新增医生」按钮仅占位提示（无真实新增）；AI 画像接口 GET /hcps/{id}/profile 已定义但页面未展示（2026-08-11 全文件审计确认）~~（2026-08-11 已修：ModalForm 真实接线 + DoctorDetail AI 画像卡片）
- 移动端：~~语音输入仍是 stub~~（2026-08-11 已修：真实链路已接 + 流式推流）；~~关键节点标记/话术建议实时推荐（需求标"后续版本"）~~（2026-08-11 已做 LLM 版：visit-service 节流推荐 + mobile 推荐区）；~~听悟 TTS 未接~~（2026-08-11 已接：NLS REST 合成 + mobile 朗读按钮）
- NLS_APPKEY 已在 .env 配置位就绪（用户填真实 AppKey 后生效；开发联调 NLS_MOCK=1，Mock 文本不落库）；说话人分离参数名（enable_speaker_identity/speaker_diarization）待真机确认
- ~~百炼 App 未发布（对话恒降级 qwen）~~（用户确认已发布，对话降级已解决）
- 真机端到端部分实测（2026-08-12：录音流式推流 / TTS / 麦克风权限 / message_id 已真机联调并修复，见 Known Gaps 已修批；说话人分离参数名待最终确认；host 已集中 mobile/src/config.ts，见 runbook 2.4）
- 短信默认仍 console（未配签名/模板 CODE 时，验证码捞 `logs/native/auth-service.log`；配齐后 `AUTH_SMS_PROVIDER=aliyun` 生效）
- 系统配置经 .env 环境变量管理（web 只读展示配置状态，不支持在线保存——见 `GET /api/v1/system/config`）
- ~~网关限流为单进程内存版（--workers 2 时每 worker 独立限额）~~（486d440 接 Redis 分布式滑动窗口，内存版仅降级兜底）；compliance 的 REQUESTS 计数未接线（可照 specialist 中间件扩展）
- **备案资质子系统挂账（2026-08-17 一期 A 收尾，勿误以为已做）**：
  - 未备案/未过审的全量使用门禁（现仅备案到期自动冻结，且**仅限 audit_status=approved 的记录**——被驳回/待审的即使日期过期也不自动冻结；未备案/审核未过是否禁用账号待老板拍板存量方案）
  - 医生资质审核（Plan B：复用 qualification review 模式，hcps 表建资质字段）
  - 备案证书 OSS bucket ACL 私有化 + 签名 URL 预览（现 education_cert/training_cert 为直读 URL）
  - 国家备案平台公开查询接口调研（filing_number 真伪校验，现为人工核对）
  - ~~培训考试字段二期接线（compliance_training_completed / compliance_exam_score / commitment_signed 已建列未接线）~~（2026-08-19 二期 F 已接线：考试 submit 回写 exam_score（仅更高分覆盖）+ training_completed（仅 passed 置 true）；承诺书 sign 回写 commitment_signed）
- **2026 办法 22 项映射挂账（2026-08-17，与 docs/compliance-2026-22items-matrix.md 第六节同口径）**：
  - 机构授权台账（拜访前校验授权状态）——待立项
  - 产品授权台账（授权外药品推广的硬校验）——待立项
  - 药企侧商业贿赂记录核查对接备案平台公示信息——待备案平台接口调研结论
- **医生端子系统挂账（2026-08-17 一期 B 收尾，勿误以为已做）**：
  - ~~chat 端点订阅校验未硬限制（一期宽松）：订阅表用于前端入口与 C 的简报回传过滤；「未订阅不可 chat」挂账~~（2026-08-20 二期 I 已收尾：doctor 角色 chat 前必须已订阅，REST PermissionError 3000 / WS 4403）
  - 医生端流式对话未做（一期 REST 问答走 `POST /api/v1/specialists/{id}/chat`；流式挂账）
  - iOS 深链（URL scheme 注册）与 iOS 构建未验证（本机无 Xcode）
  - doctor_cert 文件与 A 计划备案资质共 OSS 前缀（同 bucket、qualifications/ 对象键前缀）——若终审要求分离再改
  - C 计划（分享链接生成/追踪统计/夜间简报）已完成，见一期 C
  - ~~医生端收藏与历史（需求 5.2(4)）挂账：复用 specialist 收藏端点，二期接线~~（2026-08-20 二期 I 已收尾：mobile-doctor FavoritesScreen 复用 `/api/v1/favorites`）
  - 测试基线（2026-08-17 一期 C Task 6 全量回归实测）：auth 104（本机 Redis 已起，7 个 Lua 并发用例不再跳过）/ specialist 138 / knowledge 72 / gateway 82 / compliance 104 / mobile jest 82（9 套件，新增 share-contract + briefing-contract）/ mobile-doctor jest 6 / web build PASS / mobile-doctor assembleDebug PASS
- **分身分享+夜间简报子系统挂账（2026-08-17 一期 C 收尾，勿误以为已做）**：
  - 简报真实推送/通知未做（一期仅代表端手动查看，无站内信/短信/推送渠道）
  - 定时生成非精确到点（lifespan 用 interval 24h 近似每日一跑，未接 cron 精确到固定时刻）
  - specialist 无 rep 归属列（「我的分身」口径 = 本人创建过分享链接的分身，非分身的创建者/负责人归属）
  - 微信落地页/二维码未做（分享链接仅 medagent-doctor:// 深链，无微信 H5 落地页或二维码海报）
- **合规培训考试子系统挂账（2026-08-19 二期 F 收尾，勿误以为已做）**：
  - 培训前置"先上线不强制"为设计决策（本计划只做状态展示/回写，不做考试/承诺书门禁拦截——未培训/未签署不影响账号使用）
  - AI 出题草稿不落库（`/ai-generate` 仅返回草稿供管理端预览，人工确认后走正常入库 + 人工审核；AI 内容仅辅助）
  - 承诺书一期不接第三方 CA（平台内电子确认：勾选 + 短信验证码 + 审计留痕，无数字签名/时间戳/存证）
  - 考试题目随机抽 approved 池（无按知识点/难度分层组卷）；成绩回写仅更新更高分（保留历史最好成绩语义）
- **合规风控深化子系统挂账（2026-08-19 二期 E 收尾，勿误以为已做）**：
  - 待复核冻结是**人工裁决**（非自动）：`/specialists/review-queue`（**分身维度**）只展示近 24h 拦截 ≥5 次的分身名单，不做任何自动冻结/停用；冻结动作在 web 合规风控看板/分身监控页由 admin/manager/compliance 手动触发（`/specialists/{id}/freeze`，reason 必填 + 审计）
  - 分身拦截计数口径 = `conversations.compliance_result`（`blocked=true`），**未给 compliance_blocks 加列**；`/specialists/monitor` 的 compliance_health、`/conversations/search` 的 blocked、`/specialists/review-queue` 的聚合均读该字段
  - 官方公共数字员工创建入口**已在 web 分身监控页落地**（MonitorList ModalForm，is_official=true）；其内容管理（如批量、权限细分）后续可按需扩展
  - web 对话检索测试页未纳入本计划（knowledge-service `/search-test` 已存在，web 接线成本低但属 knowledge 域——**挂账**，下张计划或独立小任务）
  - 测试基线（2026-08-19 二期 E Task 6 全量回归实测）：auth 135 / specialist 152 / compliance 110 / knowledge 72 / gateway 82 / visit 115 / hcp 54 / audit 26（8 服务 746）+ shared 19；mobile jest 86（10 套件）/ mobile-doctor jest 6 / web build PASS
- **学术触达子系统挂账（2026-08-19 二期 G 收尾，勿误以为已做）**：
  - 推送渠道 = 站内信（notifications 表），**未接第三方推送 SDK/短信**——医生须登录后经 `/card-pushes/notifications` 查收，无实时离线触达
  - 卡片生成 = AI 辅助（qwen-max）+ 三层合规预检，**无人工审核工作流**：AI 内容经合规预检后直接落库 active，`is_ai_generated` 标注 AI 内容；管理端仅能看触达统计（/stats），无卡片内容人工复核界面
  - 代表端推送对象选择 = 数字 doctor_id（`/push` 直接传 doctor_ids 数组 ≤50）；**push-targets 可选端点（列出该代表可推送的订阅医生）未做**——前端按数字 ID 选择
  - **好评回流已落地（终审补充）**：卡片 useful 反馈 → conversation_feedback(rating=1) → 分身好评率 approval_rate（/specialists/monitor 与 /{id}/stats 口径自动计入），同 push 去重不重复写；追问/无用仅站内通知，不计好评
  - 测试基线（2026-08-19 二期 G Task 8 全量回归实测）：auth 135 / specialist 169（156 + academic_cards 6 + card_pushes 7）/ compliance 107（较 E 基线 -3，待复核名单迁 specialist 所致，非回归）/ knowledge 72 / gateway 82 / visit 115 / hcp 54 / audit 26（8 服务 760）+ shared 19 = **779 passed**；mobile jest 89（11 套件，新增 academic-contract）/ mobile-doctor jest 9（新增 inbox-contract）/ web build PASS
- **AI陪练+Skill模版子系统挂账（2026-08-19 二期 H 收尾，勿误以为已做）**：
  - ~~Skill 上架仅官方模版：skill_packages 无代表侧发布端点（创建入口 require_roles admin/manager/compliance/medical），代表发布个人 Skill 到广场 = 三期~~（2026-08-20 三期 J 已交付：`POST /release` + `GET /mine` + web/mobile 两屏）
  - 三期 J 下架语义（2026-08-20 交付，记录口径）：compliance 下架禁用已加载陪练（`practice_turn` 拦截存量会话）；author 下架已加载陪练不受影响（仅 `create_session` 拦截新用户加载）——作者申请下架不追溯已加载用户的存量会话
  - 陪练评分 = 轮数确定性基线（complete 按 turn_count 线性映射四维分，上限 0.9）；完整 LLM 深度评分挂账
  - 多轮陪练 AI 历史恒空：`practice_turn` 调 `_doctor_reply(message, skill, scenario, [])` 恒传空 history（Task 3 Minor），AI 医生看不到前文
  - 终审修复（2026-08-20）：web 创建官方模版加 is_public 开关（默认上架，`skillAPI.create` 带 is_public）；广场加载把 skill_id 经 `PracticeList` 路由参数带进陪练会话 create；补异议话术库 objection_scripts（迁移 017 + 三端点 + 陪练 turn 注入 approved 异议）；陪练 complete 补 per_turn[] + 新增 `GET /practices/progress` 进步曲线
  - 测试基线（2026-08-20 二期 H Task 7 全量回归实测）：auth 128 passed + 7 skipped（本机 Redis 未起，7 个验证码 Lua 并发用例跳过；Redis 起时 135）/ specialist 189（170 + skill 9 + practice 5 + twin_manage 5）/ compliance 107 / knowledge 72 / gateway 82 / visit 115 / hcp 54 / audit 26（8 服务 773）+ shared 19 = **792 passed**（+7 skipped）；mobile jest 94（12 套件，新增 practice-contract）/ mobile-doctor jest 9 / web build PASS
- **医生端体验子系统挂账（2026-08-20 二期 I 收尾，勿误以为已做）**：
  - 个性化学术简报为简化版（`/doctor-profiles/briefing` 仅按兴趣领域返回关键词建议，非真实内容聚合/文献推送，后续深化）
  - 患教转发前确认在 UI 层（站外转发/本人使用不经审核流、无后端站外转发端点，转发管控靠前端；**分享到患教专区已走审核流**——三期 M 交付 `/publish`（shared+pending）→ `/review`（approve/reject）→ `/zone`（shared+approved 可见））
  - learn 未按 session_id=medical_qa 过滤（Task 2 Minor）：偏好学习取本人全部 conversations（user_id 行），非仅 medical_qa 行
  - 医生侧广场热门排行口径 = 被添加数（added_count），好评率排序后续；运营统计 twin-ranking 仅 added_count 降序 + approval_rate 展示
  - 测试基线（2026-08-20 二期 I Task 8 全量回归实测）：auth 128 passed + 7 skipped（本机 Redis 未起，7 个验证码 Lua 并发用例跳过）/ specialist 219（198 + profile 6 + edu 5 + plaza 4 + chat_subscription 3 + stats 3）/ compliance 107 / knowledge 72 / gateway 82 / visit 115 / hcp 54 / audit 26（8 服务 803）+ shared 19 = **822 passed**（+7 skipped）；mobile jest 94（12 套件）/ mobile-doctor jest 15（3 套件，新增 doctor-exp-contract）/ web build PASS

**审计确认的技术债（2026-08-06，勿误以为已修；划线=已修，2026-08-11）**：
- ~~**听悟离线归档转写必然失败**：`visit-service/app/services/tingwu_client.py:83-96` 的 `_parse_result` 未处理 GetTaskInfo 返回的"带签名 URL 的 dict/JSON 字符串"结果（dict 取 None、str 抛 AttributeError）~~（6dce273 已按真实 GetTaskInfo 结构重写 `_parse_result`）
- ~~**流式答案合规审核旁路**：`specialist-service` 的 `generate_stream` 边生成边推送，答案合规审核在全文推送后才执行——被拦时违规内容已展示（REST 路径语义正确）~~（e6c0d75 起逐帧 fast 门禁，违规帧不转发）
- ~~**收藏多轮错配**：`conversations.py:77-82` 收藏锚定某轮 assistant 行，但 question/answer 取 session 第一条 → 多轮会话收藏展示错对问答~~（b63f736 以被收藏行为锚点取同轮问答）
- **无整体超时熔断**：bailian_client 每帧 wait_for 30s × 60 帧上限，最坏单条 chat 可挂约 30 分钟；证据等级为被动正则，降级（qwen）模式恒 None
- ~~**hcp mass assignment**：`hcp_repo.py:99-103` update 用 hasattr 放行任意列（可改主键/时间戳）~~（61144da API 层白名单 400 + repo 层 _filter_writable 兜底）；~~**AI 画像无缓存**（每次 /profile 付费调 qwen-max 且不落库）~~（2485943 HcpCache Redis 缓存 hcp:{id}+profile:{id}，TTL 300s，写路径失效）；`update_hcp_profile_from_visit` 的 tags 字符串按字符迭代
- ~~**knowledge 审核同步阻塞**：`review_document`/`upload_document` 在 async 端点同步执行百炼轮询（最长 1h），阻塞事件循环~~（7422a74 线程池 + 原子抢占）；PG 'simple' 分词不切中文（ts_rank 恒 0）
- ~~**compliance service_name 失真**：`rules.py:68` 把内容类型（user_input/ai_output）写进 service_name 列（调用方不传 service_name）→ 监管报告"按服务"统计显示的是内容类型；`checked_rules` 是假数据（全量规则 id 覆盖，含未执行的语义规则）~~（4e770a6 specialist/visit 客户端请求体显式传 service_name、缺省 unknown；checked_rules 只列实际执行的规则——keyword/regex 全跑、semantic 仅 LLM 真会调用时列入，无违规也返回真实覆盖面）；~~warn/log 违规也计入拦截计数~~（85aebf3 compliance_blocks_total 只计 reject，新增 violations_total 全量 + semantic 缺 key 剔除可观测，/blocks/stats 加 action 参数）
- **audit 导出 1 万条静默截断**（logs.py:155）、~~`logger.log()` 无 `**kwargs`（调用方新增字段键会 TypeError 被吞）~~（2026-08-11 十项缺陷 #3 已加 **kwargs 吸收）；~~`AUDIT_LOG_RETENTION_DAYS` 死配置~~（f50a8de lifespan 定时清理 + medagent_audit_cleanup 专职角色，迁移 005 需 superuser）
- 网关 JSON 分支内容长度经 `response.json()` 重序列化后透传上游 content-length（当前全栈 FastAPI 字节一致，属潜在失配）

**2026-08-11 全量审计（8 域 8 代理并行，60 发现合并去重，用户确认仅归档暂缓修复；划线=已修）**：
- ~~**H1 JWT_SECRET 静默默认回退 + 6 业务服务无 fail-fast 守卫**：`shared/common/auth.py:29,48` `os.getenv("JWT_SECRET", "dev-secret-change-me")` 同时用于 create_token/verify_token，specialist/visit/knowledge/compliance/hcp/audit 均无启动守卫（仅 auth/gateway 有）→ 漏配时可用公开密钥伪造任意角色 token 直连 8001-8007。修法：守卫下沉 shared 或各服务 main.py 统一 fail-fast，默认回退从 shared 移除~~（2026-08-11 已修：shared `WEAK_JWT_SECRETS` + `validate_jwt_secret` fail-fast，6 服务 main.py 启动守卫，config 默认值删除，test_jwt_failfast.py 回归）
- ~~**H2 停用/降级账号旧 token 7 天内仍有效**（require_roles 实时查库只覆盖受限端点）：`get_current_user`（auth.py:64-74）只信 token 快照 → 停用 admin 旧 token 可经 admin 旁路操作他人收藏/对话（`conversations.py:30,163` 的 `current_user.get("role") != "admin"`）、knowledge 未上架文档可见性（`_can_view_all_documents` 读 token role）、visit WS/REST 归属与 admin 判定、specialist/visit 两个 WS 端点。修法：状态/角色查库下沉 get_current_user 与 WS 鉴权公共路径~~（2026-08-11 已修：get_current_user 每次请求主键查库 401 code 2003，chat_ws/asr_ws 同语义 4401，specialist/visit/audit/auth 停用用例）
- ~~**H3 hcp /profile 画像跨用户泄露**：`hcps.py:93-125` 只挂 get_current_user（无角色限制）；`profile_generator.py:46` 调 `list_interactions(db, hcp.id)` 不传 user_id（SQL `:user_id IS NULL` 不过滤，注释写明"仅 admin/manager 使用"但接口未接角色校验）→ 任意 rep 可拉含全部代表互动细节（ai_summary/key_points/objections）的画像，profile:{id} 全用户共享缓存。修法：接口挂 require_roles 或按 user_id 过滤~~（2026-08-11 已修：admin/manager 全量 :all，rep 本人 :u{uid}，缓存分键 + scan_iter 前缀失效，profile_generator user_id 过滤）
- ~~**H4 knowledge 审核状态机竞态**：`document_manager.py:142` approve 抢占 processing（百炼导入最长 1h）后 `update_status(doc_id, "ready")` 无条件写终态；reject 允许 draft/processing/ready 驳回（:190）→ 审核期间驳回/归档被 1h 后翻回 ready 重新上架。修法：终态条件更新（`WHERE status='processing'`），驳回同样原子抢占~~（2026-08-11 已修：try_mark_final/try_restore_status 条件更新，approve_without_bailian 补同锁，竞态单测 2 例）
- **H5 mobile 全链路明文 HTTP/WS**：`client.ts:10`/`wsChat.ts:7`/`asr.ts:10` JWT 与患者对话明文传输可被中间人截获
- **H6 WS token 明文 query string + 网关 WS 零鉴权零限流**：`gateway main.py:362-381` proxy_chat_ws accept 前不验 token 不限流，token 原样透传上游；mobile `wsChat.ts:42`/`asr.ts:33` 拼 URL；specialist `chat_ws.py:58`、visit `asr_ws.py:73-85` 依赖 query token。修法：网关握手前验 token + 按 user_id 限流，token 改 Sec-WebSocket-Protocol 或首帧
- ~~**M1 compliance 语义层 fail-open 覆盖"内容拒审"**：`checker.py:336-352` fail-closed 元组只收 (JSONDecodeError, KeyError, TypeError, ValueError)，内容过滤/拒答以 HTTP 400（BadRequestError，属 Exception）落入宽 except fail-open → R003/R004/R006 整体跳过，与 S7 口径冲突~~（B5 批 2026-08-12 已把宽 except 收敛为 R999 fail-closed，2026-08-13 复核确认已修并补划线）
- ~~**M2 compliance Unicode 变体绕过**：`checker.py:232-243` 匹配前无 NFKC/零宽字符剥离 → "１００％有效"、插 U+200B、"返 点"绕过 R001/R002，且 fast 流式门禁只跑文本层整体跳过~~（2026-08-13 已修：内容与规则 pattern 双端 NFKC 归一化 + 38 项零宽字符剥离（含 FE00-FE0F 变体选择符/bidi 隔离符/HANGUL FILLER 及其 NFKC 映射 U+1160），fast/full/test_rule 三路径同口径，语义层仍吃原文；纯零宽 pattern 丢弃防全量误报；终审修复 pattern 同口径与零宽表扩充）
- ~~**M3 compliance 同步 LLM 阻塞事件循环**：`checker.py:287-295` 同步 create 跑 async 端点（默认超时 600s）→ LLM 变慢时 specialist/visit 调用方 10s 超时系统性 fail-open~~（2026-08-13 已修：/check 与 /rules/test 改 asyncio.to_thread + OpenAI 客户端 timeout 15s/max_retries=1，超时仍走 R999 fail-closed；test_check_async_blocking.py 5 用例）
- **M4 compliance xlsx 导出公式注入**：`report.py:43-47` 拦截明细/规则快照原样写入 → `=HYPERLINK(...)`/`=cmd|` 开头内容按公式执行；audit 导出（logs.py:178-190）字符串列同理。修法：`= + - @ \t \r` 开头前置单引号或强制 data_type='s'
- ~~**M5 visit full_transcript 可覆盖真实转写**：`visit_manager.py:515-517` 客户端提交整段覆盖 conversation_transcript 且覆盖后不再过合规检查 → 被标记过 R002/R006 的对话可被洗白~~（2026-08-13 已修：full_transcript 必须以现有转写为前缀（追加语义，篡改拒绝 ParamError），新增部分过合规并累加 compliance_flags，与 F5 尾缀去重/状态守卫兼容）
- ~~**M6 visit follow_up 结构化输出零合规检查**：`visit_manager.py:561-569` 只查 ai_summary，key_points/hcp_interests/hcp_objections/follow_up_suggestions/next_visit_plan 及自动建任务完全不过合规~~（2026-08-13 已修：结构化字段拼合过 check_compliance——reject 清空字段/不建任务/不推画像+审计留痕，warn 照常落库+flags 累加，客户端异常按 reject 处理；终审修复 summary 被拦分支同样不推画像）
- ~~**M7 visit LLM prompt 注入**：`visit_manager.py:336-359/519-537/622-636`、`objection_detector.py:92-93` 用户可控转写/画像/历史无 `<user_content>` 定界直接内插（与 compliance S7 已修标准不一致）~~（2026-08-13 已修：prepare_visit/end_visit/follow_up/_llm_recommend/objection_detector 五处全部按 S7 同措辞包 <user_content> 定界 + system 声明）
- **M8 specialist fast 门禁不覆盖语义层**：违规内容在 full 复核前到达客户端（fast 只跑 keyword/regex）
- **M9 密码登录无账号级失败锁定**：`auth.py:263-272` 仅受网关 60/min/IP 限流，轮换 IP 可无限试弱密码。修法：Redis 账号级失败计数 + 临时锁定
- **M10 网关限流不读 X-Forwarded-For**：`rate_limiter.py:154-158` 取 request.client.host → 反代部署下全站共享一桶，刷 login/send-code 可整体 DoS
- ~~**M11 网关 `..` 路径归一化绕过公开前缀**：`main.py:257` + `auth_middleware.py:110-116`，`/api/v1/auth/login/../../docs` 命中 PUBLIC_PATHS 免 JWT 且 httpx 建连归一化 → 未认证可拉全部 7 后端 /docs、/openapi.json、/metrics~~（2026-08-13 已修：鉴权中间件在 PUBLIC/INTERNAL 匹配前拒绝 dot-segment 路径（urlsplit+逐段比对，覆盖 `/../`、`/./`、%2e 编码），400 code 1000；17 用例含零转发断言）
- **M12 knowledge 解压炸弹**：50MB 只管压缩体积，`document_processor.py:8-33` 解压/渲染到内存无输出上限 → approve 线程池撑爆。修法：页数/文本长度硬上限 + 解析超时
- **M13 hcp Excel 批量导入无大小限制**（zip 炸弹）
- ~~**M14 visit ASR WS 直连 8002 无连接数/帧大小/时长限制**（绕过网关限流，每条连接拉一条 NLS 付费会话 + conversation_transcript 无限追加 + 无界并发合规调用）~~（2026-08-13 已修：全局并发 10/单用户 2（单进程近似）、帧 256KB、空闲 90s、时长 6h，超限 error 帧 + 4500；连接数检查在开 NLS 会话之前、状态守卫之后；close 纳入 send_lock 防与合规帧并发写）
- ~~**M15 visit 合规内部调用与用户请求共用网关 IP 限流配额**：`rate_limiter.py:145-171` 内部路径无豁免 → 多 ASR 并发超 60/min 后合规 429~~（2026-08-13 已修：rate_limiter 豁免 INTERNAL_PATHS 三条内部路径（精确匹配或子路径口径，audit/logs 不误豁免）；内部路径仍强制 X-Internal-Key 双重校验，PUBLIC_PATHS 不限流豁免；test_rate_limiter_internal.py 8 用例）
- **M16 specialist chat 无长度/并发限制**（网关 WS 绕过限流）
- **M17 web localStorage JWT 无 CSP + 前端零角色访问控制**（`client.ts:10`/`AuthContext.tsx:37`；`App.tsx:43-64` 路由守卫只验登录态）
- ~~**M18 specialist /live-status question_snippet 跨用户**（`specialists.py:101` + `activity_registry.py:54`）~~（B5 批 2026-08-12 已修：非 admin/manager 剥离 snippet，2026-08-13 复核确认已修并补划线）
- **Low 批**（归档）：mobile release debug 签名（build.gradle:53-60）/AsyncStorage 明文 JWT/无 FLAG_SECURE/~~401 无全局登出~~（已实现：client.ts onUnauthorized + AuthContext 全局登出，仅 401/2000-2003 触发）；web CORS `*`+credentials（gateway main.py:68-69）、/health 泄露 backends 内网拓扑（:147-165）；specialist draft/disabled 专员配置对所有登录用户可见、默认 DB 口令硬编码（db_session.py:13-16）、/metrics 无鉴权；knowledge 上传仅校验扩展名不校验魔数（XSS 载体）、/search-test 泄露内部异常、/stats 泄露云资源 ID 与未上架计数、检索参数健壮性（product_id 非法值静默丢过滤/无长度限制）、feedback doc_id 不校验、被驳回文档百炼索引未清理（降级路径仍可命中）；compliance 报告导出无上限（report.py:90）、正则 ReDoS 可入库（rules.py:90-95）、审计 client_ip 信 XFF 首段（logs.py:280-285）、拦截记录/审计 JSONB 明文留存敏感片段；visit audio_url 无 scheme/域名校验（tingwu_client.py:50-53 SSRF/费用滥用）、end_visit 状态锁非原子 + 任务幂等 TOCTOU、NLS 会话失败静默吞掉无 error 帧、任务状态变更无审计日志；auth 验证码取号/作废非原子（code_store.py:92-111 并发可用两次）、审计 client_ip 可被 XFF 伪造

## Backup & Restore（2026-08-12 新增）

- **每日自动备份**：`scripts/backup_db.py` —— pg_dump -Fc 全量 → pg_restore --list 校验 → OSS 上传（ACL 私有）→ 本地 7 天 / OSS 30 天过期清理。ECS crontab：
  `0 2 * * * cd /opt/medagent && python scripts/backup_db.py`
  （**不要加 `>> logs/backup.log 2>&1`**：脚本 log() 已自写 backup.log，加重定向每行日志双写）
- **ECS 上线顺序**：① 以 medagent_root 执行 `scripts/migrations/007_grant_audit_seq.sql`（002 降级后 medagent 无 superuser 无法自行 GRANT，缺了首次备份必挂）→ ② .env 填 OSS_* 凭证 → ③ 配 cron → ④ 手动跑一次 `backup_db.py` 验证
- **失败留痕**：`logs/backup.log` 追加 + `logs/backup-failed` 标记文件 + 非零退出码。可用 cron MAILTO 或阿里云 CloudMonitor 自定义监控检查标记文件感知失败；开发环境无 OSS 凭证时用 `--local-only`（本地备份+校验，不上传）
- **恢复验证**：`python scripts/restore_db.py --source local|oss [--dump 文件] [--target-db 库] [--yes] [--pg-user 用户]` —— 默认恢复到 `medagent_restore` 临时库并校验 users/conversations/audit_logs 行数，**不自动覆盖生产库**；`--target-db` 仅允许 `[A-Za-z0-9_]+`（防注入）。恢复生产库：停服务 → `DROP DATABASE medagent WITH (FORCE)` → restore --target-db medagent --yes → 启服务
- **2026-08-13 修复**：ensure_target_db 的 CREATE DATABASE 改用 `--pg-user`（默认 medagent）。生产已执行 002 降级后 medagent 无 CREATEDB，恢复演练/灾备必须 `--pg-user medagent_root` 并配置 `PG_ROOT_PASSWORD`（.env.example 已有配置位；未配时 RuntimeError 不静默回退）。OSS 30 天过期清理正则已与秒级文件名一致（\d{6}）
- **恢复后注意**：audit_logs 所有权/权限（002 审计不可篡改迁移）需在新库重新执行；Redis 不备份（缓存数据可重建）；二进制输出经 docker exec 直写文件（Windows CRLF 安全）
- **2026-08-12 已验证**（本机全链路真实）：备份→校验→OSS 上传/过期清理（含删除测试对象无残留）→ 恢复 local+oss 双源三表行数一致（users 2/conversations 178/audit_logs 1418）→ 失败留痕三路径（dump 损坏/取消/非法库名均非零退出）→ 007 幂等重跑

## Gotchas

- **Docker build context 是仓库根目录**：所有镜像都要 `COPY shared/`，所以 Dockerfile 里的路径都写成 `services/<name>/...`，构建时用 `docker build -f services/<name>/Dockerfile .`。docker-compose 里已配好 `context: .`。
- **容器内不能用 localhost**：`.env` 里的 `DATABASE_URL`/`REDIS_URL`/`GATEWAY_URL` 是给宿主机直跑 uvicorn 用的。docker-compose 用 `environment` 覆盖成 compose 服务名（`postgres`/`redis`/`gateway`）。
- **`JWT_SECRET` 必须配**：auth-service 检测到未配置或仍是默认值会拒绝启动（否则会签出可伪造的 token）。生成：`openssl rand -hex 32`。
- **`INTERNAL_API_KEY` 必须配**：`shared/common/internal_auth.py` 检测到未配置或默认值会抛 RuntimeError —— 网关/所有服务都依赖它做内部接口鉴权。生成：`openssl rand -hex 32`，网关与所有服务必须一致（`env_file: .env` 天然保证）。
- **`AUTH_DEV_MODE=true` 只能本地用**：打开后 `send-code` 会在响应体里回传验证码。
- **验证码存 Redis，不 fail-open**：Redis 挂了 `send-code`/`login` 直接返回 5004，不放行。
- **Windows GBK 控制台**：不能输出 ✓ / ✔ / emoji，否则 `UnicodeEncodeError`。用中文标记代替（如"达标"）。
- **测试从服务目录跑**：`sys.path` 依赖 `os.path.join(__file__, "..", "..", "..")` 找到 shared，从项目根目录执行会 `ModuleNotFoundError: No module named 'app'`。
- **SQLite 单测建表要限定表名**：`shared.models` 里 products/hcps 等用了 PostgreSQL 的 JSONB，SQLite 渲染不了；且 `TimestampMixin` 的 `BigInteger` 主键在 SQLite 下不自增，需显式给 id。内存 SQLite 还要用 `StaticPool` 才能跨 session 共享。参考 `services/auth-service/tests/test_auth.py`。
- **JWT 用 PyJWT（`import jwt`）**：`requirements.txt` 里声明的是 `PyJWT>=2.8.0`。历史上写过 `python-jose[cryptogram]`（拼写错误的空 extra，且代码从未 import jose），已全部清除，不要加回来。
- **服务间调用绕网关**：不要在代码里写 `http://localhost:8004` 调合规服务，走 `GATEWAY_URL + /api/v1/compliance/check`，否则 JWT 认证会拦截（除非已加入 Gateway 白名单）。
- **合规规则文件路径**：`RULES_YAML_PATH` 环境变量指定，容器内是 `/app/shared/compliance-rules/rules.yaml`。加载到 0 条规则会打 ERROR —— 那是"全部放行"的危险状态。
- **`.env` 在 `.gitignore` 中**：根目录 `.env` 不会被提交，模板见 `.env.example`。
- **hcp-service 的 visit_interaction_repo**：同库直读 `visit_records` 表（避免循环依赖），表不存在时降级为空列表。如果 visit-service 和 hcp-service 不在同一个 DB，需要改为 HTTP 调用。
- **visit_records 有 status 列**（迁移 008 新增，2026-08-13 起已并入 init_db.sql）：completed/in_progress 语义仍从 ai_summary 推导（占位串 ≠ 已结束，可重试 end），cancelled 是显式状态；旧库须跑 006/008。
- **前端字段 camelCase、后端 snake_case**：映射统一收在 `mobile/src/api/*.ts`（`prepareVisit` 等已修，2026-08-06 实测 pre-visit 200）。改后端 schema 或响应形状时，同步改 api 层 + 契约测试，屏幕组件只消费 api 层的映射结果，不直接碰请求体。
- **跨服务 FK 需要注册元数据**：`visit_records` 的 FK 引用 hcps/products/digital_specialists，visit-service 必须 import `shared.models.hcp`/`product`/`digital_specialist`（见 `services/visit-service/app/models/visit_record.py`），否则 SQLAlchemy 报 `NoReferencedTableError`。共享模型放 `shared/models/`，各服务 `app/models/*.py` 是 re-export。
- **Commit 格式**：遵循 conventional commits `feat(scope): subject`，末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`。
- **005 迁移（audit 清理角色）需 superuser**：002 后无 superuser，GRANT DELETE 会失败；现场已用 `postgres --single` 单用户模式建 `medagent_root`（rolsuper=t，NOLOGIN）与 `medagent_audit_cleanup`（仅 SELECT+DELETE on audit_logs），应用账号仍仅 INSERT/SELECT。新环境跑 005 前先造 superuser（停容器 → `echo "SQL" | postgres --single -D <datadir> medagent`，-c 参数会被 entrypoint 截胡）。配套环境变量 `AUDIT_CLEANUP_DATABASE_URL`（medagent_audit_cleanup 账号专用连接串，.env.example 已有，默认占位密码 medagent123）。
- **EMBEDDING_DIM 已硬编码 1024**（`knowledge-service/app/services/dashvector_client.py`）：text-embedding-v3 最大 1024 维，collection 已按 1024 重建；别改回 1536，改维度必须删除重建 collection（删了会自动重建）。**ES_URL 未进 .env.example**（代码 `os.getenv("ES_URL", "")` 读取，配了才启用 ES 检索路径，现环境未启用）。
- **shared/prompts/oncology_specialist.yaml 是孤儿资源**：话术模板文件，目前无任何服务加载（main.py 均未引用），改动它不会影响任何行为。
- **web/ three 是唯一需拍板的额外依赖**：3D 办公室引入（老板拍板打破零依赖约定；axios/dayjs/react-router-dom 属常规框架依赖），新增前端依赖需同样先问；@types/three 在 dependencies 而非 devDependencies；`t10-office3d/e2e_v4.py` 的 `project()` 与布局/相机强耦合，改了 `OfficeScene3D.tsx` 相机或 `layout.ts` 布局常量必须同步改 E2E 投影，否则 sit 断言必挂。
- **Metro 打包失败 = App 白屏/无法加载**：任何相对路径 import 解析失败（如 `SettingsScreen.tsx` 的 `require('../../package.json')` 少一层 `../`，2026-08-11 623a6cb 修复）会让整个 bundle 挂掉，`metro.log` 里 `Unable to resolve module ... from <file>` 即定位点；改完代码 App 不会自动重拉 bundle，需 `adb shell am force-stop com.medagent.mobile` 后重启 App。
- **NLS TTS 合成**：mobile 直调 `https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts?appkey&token&text&format=wav&sample_rate=16000`（REST 一次性合成，非流式）；appkey 非机密可放客户端，AK/SK 永不出服务端
- **mobile/ react-native-sound 是首个音频播放依赖**（TTS 朗读；原生模块需重新 run-android）
- **transcript 响应含 key_nodes/ai_suggestion**（LLM 推荐节流 20s/句；失败返回空数组/null 不阻塞）
- **`QUALIFICATION_CHECK_INTERVAL_HOURS`**（auth-service 备案到期扫描周期，默认 24 小时、可省略不配）：启动即跑一次，此后每 N 小时扫描 `representative_qualifications` 的 filing_expire_date < 今天 且 role=rep/status=active **且 audit_status=approved** 的代表，**自动冻结账号**（status→disabled）+ 审计 action=qualification_expired_freeze；审计失败不阻断冻结。**到期日未经人工审核通过（pending/rejected）的代表即使日期过期也不自动冻结**——冻结只对审核结论做强制执行，不替代人工裁决（2026-08-17 终审修复 F4）。filing_status 本身是派生值不落库。
