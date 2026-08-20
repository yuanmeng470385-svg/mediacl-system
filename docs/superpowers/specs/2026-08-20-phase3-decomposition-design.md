# 三期需求拆解设计（2026-08-20）

> 依据：`C:\Users\yuanmenglong\Desktop\AI数字员工架构及功能设计.md`（2026-08-17 修订版，老板已确认）
> 二期五计划（E 合规风控 / F 培训考试 / G 学术触达 / H AI陪练+Skill / I 医生端体验）已于 2026-08-19/20 全部交付并推 Codeup。
> 本设计把三期（"建生态，形成竞争壁垒"，需求第八章第三期）拆为 5 张可独立交付的实施计划（J/M/N/K/L），复用二期 SDD 流程。

## 1. 范围

三期共 10 项能力（管理后台 6 + 代表端 2 + 医生端 2），跨 5 个业务域，拆为 5 张计划。核心主题：从"功能可用"升级为"平台生态 + 合规治理成熟"。

### 明确不进三期的后续边界

- 第三方 CA 电子签（承诺书仍为平台内电子确认）
- 积分兑换加载 Skill（需求标后续版本）
- 飞书/微信集成（用户暂缓）
- 医生端流式对话（一期 B 挂账，仍挂账）
- 统方数据（全平台零留存，不统计/不展示/不导出处方量）

## 2. 通用决策

1. **Skill 内容字段落地**（已拍板：风格+说明+话术内容）：`skill_packages` 新增 `description VARCHAR(200)`（治疗领域/一句话说明）与 `content TEXT`（个人话术/prompt 素材，审核维度）。**内容与权重任何 API 不返回**、常规管理员不可见、仅审核人 `detail` 受控查看 + 访问审计；公共广场仅元数据（名称/创建者/治疗领域/风格标签/热度/好评率）。忠实附录 A "skill_weights 与内容字段任何 API 均不返回"。
2. **数据分类分级实现深度**（已拍板：清单+按类别管控导出）：web「数据治理」页展示三类数据资产清单（个人信息/业务数据/合规留存数据，映射实际表，只读配置）；**敏感类别（个人信息/对话明细）导出必走审批流**；报表导出（非敏感）保持直出。不做字段级打标。
3. **数据导出审批范围**（已拍板：报表直出+敏感导出走审批）：现有报表（监管自查/触达统计/运营统计）直接导出；新增敏感导出物走审批流 = ① 对话明细 xlsx（管理端申请）② 医生个人数据包（应医生导出请求，走隐私请求流）。审批人=合规部（admin/manager/compliance），3 工作日 SLA，流程留痕（申请→审批→导出记录）。
4. **医生数据删除/注销执行方式**（已拍板：去标识化+禁用+留存）：姓名/手机号等标识信息即时脱敏（`full_name`→"已注销医生"、`phone` 脱敏），账号禁用不可登录、token 失效，历史业务与审计数据物理留存至法定期满（个保法留存例外条款），处理过程留痕。
5. **合规铁律贯穿**：AI 生成内容全部标注"AI 生成"；三层合规预检走既有 `compliance /check`（fail-closed）；引用无页码（以挂载元数据为准）；权限走 `require_roles` 实时查库；`<user_content>` 定界（新增 LLM 调用必须应用）。
6. **留存铁律**：对话/审计留存期内不可修改、不可删除；删除请求先删/去标识化账号标识信息，历史数据留存至法定期满（对齐 3.8(5)）；现有 `AUDIT_LOG_RETENTION_DAYS` 清理按此策略对齐（清理只针对超期数据）。
7. **流程**：每张计划 = 需求章节 → writing-plans 出 plan → SDD 逐任务执行 + 逐任务审查 + fable 终审 + 修复闭环 → 推 Codeup；CLAUDE.md / README 收尾同步。执行顺序 **J → M → N → K → L**。
8. **迁移独立**：每张计划一张迁移（019-023），旧库须按序执行，`init_db.sql` 同步。

## 3. 计划 J：Skill 生态闭环（需求 3.6/4.7/6.4）

**目的**：把二期"官方模版供给"升级为"代表发布 → 管理审核 → 广场供给 → 下架禁用"全生态闭环。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| 迁移 019 | 附录A/3.6 | `skill_packages` 加 `description`/`content`/`off_shelf_status`(active/off_shelved)/`off_shelf_reason`/`off_shelf_type`(compliance/author)/`off_shelf_by`/`off_shelf_at`；新表 `skill_off_shelves`（下架记录存档：skill_id/operator_id/type/reason/created_at） |
| 代表发布 Skill | 4.7(4)/6.4(1) | `POST /api/v1/skill-packages/release`（require_roles rep；name ≤100 + description 治疗领域 + content 话术素材 + style_tags + skill_weights + is_anonymous；audit_status=pending；审计 action=skill_release） |
| 我的 Skill | 6.4(6) | `GET /api/v1/skill-packages/mine`（rep 本人 Skill 列表：审核状态 + 热度数据 heat/approval_rate/加载数） |
| 管理资产列表 | 3.6(1) | `GET /api/v1/skill-packages/asset-list`（管理四角色；全部 Skill 含代表发布，元数据 + 创建者姓名/角色 + off_shelf_status 过滤） |
| 审核 | 3.6(2) | 复用现有 `POST /{id}/review`（审核人 detail 受控查看 description/content/weights + **补访问审计**）；审核状态 pending/approved/rejected |
| 下架 | 3.6(3) | `POST /api/v1/skill-packages/{id}/off-shelf`（管理四角色；type=compliance|author 必填、reason 必填 ≤500；写 skill_off_shelves + audit action=skill_off_shelf）；**compliance 下架 → 已加载该 Skill 的陪练场同步禁用并提示原因**（practice_turn 校验 off_shelf_status + reason）；**author 下架 → 已加载用户不受影响、新用户无法加载**（load/public 列表过滤 off_shelved） |
| 热度数据 | 6.4(6) | 发布者 mine 列表可看 heat/approval_rate；`/public` 排序复用 heat |

**边界**：Skill 内容/权重仅审核人受控可见（隐私铁律不变）；下架不做自动触发，人工裁决。

## 4. 计划 M：患教专区审核流（需求 5.5(3)/3.9(2)/附录A）

**目的**：二期"预审模板+AI 标注+默认仅本人可见"升级为"分享到平台专区须过审核，专区可见"。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| 迁移 020 | 附录A | `edu_content_records` 加 `audit_status VARCHAR(20) DEFAULT NULL`（NULL=未分享；分享→pending，审核→approved/rejected；值域对齐需求附录 A 三值枚举，不新增'private'混淆值——已分享与否由既有 `visibility` 表达） |
| 分享到专区 | 5.5(3) | `POST /api/v1/patient-edu/{id}/publish`（require_roles doctor，仅本人；visibility→shared + audit_status→pending；仅生成记录可分享；审计 action=edu_publish） |
| 撤回 | 5.5(3) | `POST /api/v1/patient-edu/{id}/unpublish`（仅本人；audit_status=approved 前可撤回 → 回 private；已审核通过的进入专区的内容撤回 → 专区不可见） |
| 审核 | 3.9(2) | `GET /api/v1/patient-edu/review-queue`（管理四角色；audit_status=pending 分页，含医生姓名/科室）+ `POST /api/v1/patient-edu/{id}/review`（approve/reject，reject 必填 reason ≤500，仅 pending 可审，审计 action=edu_review） |
| 患教专区 | 5.5(3) | `GET /api/v1/patient-edu/zone`（require_roles doctor；visibility=shared + audit_status=approved 分页浏览，内容展示完整卡片） |

**边界**：本人使用与站外转发不经过平台审核流（依赖模板预审 + AI 标注）；患教内容不采集患者诊断/用药（既有铁律）。

## 5. 计划 N：陪练 LLM 深度评分与逐句反馈（需求 4.5(4)）

**目的**：把 complete 的"轮数确定性基线评分"升级为 LLM 真实逐句反馈 + 改进建议。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| 迁移 021 | 4.5(4) | `practice_sessions` 加 `transcript JSONB`（逐轮 Q&A 落库：[{turn, role, content}]，现 turn 只计数不存内容） |
| 对话落库 | 4.5(2) | `practice_turn` 成功后把 {role:'rep', content:message} 与 {role:'ai', content:ai_msg} append 进 session.transcript（history 恒空既有决策不变，落库不影响） |
| LLM 深度评分 | 4.5(4) | `complete` 升级：基于完整 transcript 调 qwen（`<user_content>` 定界）生成四维评分（evidence_accuracy/objection_handling/communication_logic/overall）+ **per_turn 逐句反馈**（每轮改进建议，真实化替代确定性基线）+ 汇总建议；LLM 失败降级回确定性基线（fail-safe，不阻塞） |
| 进步曲线 | 4.5(4) | 复用既有 `GET /api/v1/practices/progress`（聚合 completed sessions.scores） |
| 代表端 | 4.5(4) | 陪练结果页展示逐句反馈 + 改进建议（PracticeChat 完成态扩展） |

**边界**：陪练 AI 历史仍恒空（既有 Task 3 Minor 挂账，本计划只落库不注入）；不做微调模型。

## 6. 计划 K：MAH 全景视图 + 数据治理（需求 3.7(4)(6)/3.8(1)(2)(3)）

**目的**：药企主体责任视角（MAH 合规全景）+ 数据资产分级与敏感导出审批流。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| MAH 合规全景视图 | 3.7(4) | `GET /api/v1/specialists/mah-overview`（**specialist-service**，require_roles admin/manager/compliance；**架构修正：conversations 模型在 specialist-service，合规通过率口径（compliance_result.blocked=true）同 review-queue 先例，故与 review-queue 同居 specialist，不走 compliance-service**；聚合所有代表）：备案状态分布（valid/expired/not_filed + audit_status 分布）、合规培训完成率（exam 通过 + commitment 签署比例）、合规通过率（1 − conversations.blocked/total） |
| 数据分类分级 | 3.8(1) | `GET /api/v1/compliance/data-assets`（只读配置清单：个人信息 users/doctor_profiles/doctor_twin_subscriptions + 业务数据 conversations/academic_cards/edu_content_records/card_push_records + 合规留存 audit_logs/compliance_blocks/compliance_rules；返回类别→表→字段级别说明） |
| 数据导出审批 | 3.8(3) | 迁移 022 `export_requests` 表（requester_id/export_type/reason/status pending/approved/rejected/approver_id/approve_reason/created_at/responded_at/expires_at；一期 export_type 仅 `conversations` 对话明细一种敏感导出物，报表直出不入表）；`POST /api/v1/data-exports/requests`（**admin/manager 申请**）+ `GET /api/v1/data-exports/requests`（分页/状态过滤）+ `POST /{id}/review`（**合规部审批**=admin/manager/compliance；approve 后生成对话明细 xlsx 落 OSS + 导出记录 + 审计；SLA=created_at+3 自然日，超时未审列表高亮提醒，**不自动放行**）+ `GET /api/v1/data-exports/requests/{id}/download`（审批通过后下载，带 expires_at 过期）；对话明细导出 = specialist-service（同库直读 conversations，仅 approved 后生成，导出列含 代表/医生/分身/时间/内容/compliance_result，绝不含患者诊断信息） |
| 数据访问审计 | 3.8(2) | Skill 审核查看行为写访问审计（J 计划 skill_detail 补）；本计划确认导出/审批动作全量走既有 audit_client 留痕 |
| web | 3.7(4)/3.8 | MAH 全景视图页 `/compliance/mah-overview` + 数据治理页 `/data/assets` + 导出审批页 `/data/exports` |

**边界**：不做字段级打标；导出物一期仅对话明细（医生数据包在 L）；审批超时不自动放行（人工裁决，3 工作日 SLA 仅提醒）。

## 7. 计划 L：隐私中心（需求 5.7/3.8(4)(5)）

**目的**：医生端完整隐私管理中心 + 管理后台请求处理（30 日 SLA），删除/注销按去标识化+留存执行。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| 迁移 023 | 3.8(5)/附录A | `privacy_requests` 表（doctor_id/request_type view/correct/delete/export/account_delete/status pending/processing/done/rejected/content JSONB(申请内容/回复)/responded_at/handled_by/handled_at/sla_deadline 30 日）；`users` 加 `deleted_at`（注销标记，status 复用现有值域扩 deleted） |
| 医生端隐私中心 | 5.7(1)(2)(3) | 隐私政策全文（静态文案，auth-service 配置端点）；个人信息查看（GET /doctors/personal-data：user + doctor_profile）；历史对话查看（复用 favorites/conversations 历史）；申请更正（手机号/姓名 → 提交 privacy_request type=correct）；申请导出（type=export → 管理端处理后提供数据包）；申请删除（type=delete）；申请注销（type=account_delete，注销前强制确认） |
| 请求提交/查询 | 3.8(4) | `POST /api/v1/privacy-requests`（require_roles doctor）+ `GET /api/v1/privacy-requests/me`（本人请求分页 + 状态） |
| 管理后台处理 | 3.8(4) | `GET /api/v1/privacy-requests`（admin/manager/compliance 分页 + 状态/类型过滤 + 30 日 SLA 超时高亮）+ `POST /{id}/handle`（处理留痕：correct→更新 user 字段、export→生成数据包、delete/account_delete→执行去标识化，handled_by/handled_at/response 必填；审计 action=privacy_request_handle） |
| 删除/注销执行 | 3.8(5) | 去标识化（full_name→"已注销医生"、phone→脱敏掩码）+ status→deleted + deleted_at + token 失效（auth 实时查库天然拦截）+ 历史留存；管理员可查处理留痕 |
| web | 3.8(4) | 隐私请求处理页 `/privacy/requests` |

**边界**：不做物理删除（法务风险，已拍板去标识化+留存）；查阅/更正以自助为主、敏感字段（手机号）走请求流。

## 8. 依赖与执行顺序

```
J Skill生态 ──► M 患教专区 ──► N 陪练LLM评分 ──► K MAH全景+数据治理 ──► L 隐私中心
 (独立)        (独立)        (独立)             (独立)                 (独立)
```

- **J**：无前置依赖，生态闭环先做（代表 Skill 发布/审核/下架）。
- **M**：无前置依赖（edu_content_records 建 audit_status 列即可启用）。
- **N**：无前置依赖（practice_sessions 加 transcript）。
- **K**：无前置依赖（export_requests 新表；MAH 全景聚合既有 compliance_blocks/conversations）。
- **L**：无前置依赖（privacy_requests 新表 + users.deleted_at）；医生导出请求的处理物（个人数据包）逻辑独立实现。

五张计划间无硬依赖，各自独立交付，顺序仅按业务价值排列（生态闭环先行，数据治理殿后）。

## 9. 风险与注意

- **路由声明顺序（FastAPI 静态 vs 动态路由）**：J 的 `/release`/`mine`/`asset-list`、M 的 `/review-queue`/`zone`/`publish` 等静态路由**必须声明在既有 `/{id}` 动态路由之前**，否则 `/{id}` 会先匹配静态段报 422（同 specialist `live-status` 先例）。执行时写进 plan 的显式检查项。
- `skill_packages` 新增 content/description 是隐私敏感面扩大：**确认既有 `to_dict()` 默认不暴露**，仅 `detail`（审核人）与 mine/asset-list 元数据白名单字段可返回，绝不可在 `public` 广场返回内容。
- 陪练 transcript 落库可能累积对话正文：不涉及患者数据（陪练是模拟场景），但需确认不为对话隔离边界引入新数据面。
- LLM 逐句评分失败必须降级回确定性基线（fail-safe，不阻塞 complete），避免陪练完成卡死。
- 去标识化执行要防误伤：仅对目标 doctor 操作，不触碰代表/管理员；手机号脱敏要保留唯一性约束不冲突（`phone` 列可空且非唯一——users.phone 无唯一约束，脱敏串需确保不撞既有脱敏串）。
- 导出审批超时仅提醒不放行（人工裁决，对齐待复核冻结的既有原则）。
- 每张计划保持既有验证门：后端 pytest 全量 + mobile jest + mobile-doctor jest + web build + assembleDebug。

## 10. 交付产物

每张计划（J/M/N/K/L）独立：
- 实施计划文档 `docs/superpowers/plans/2026-08-20-<plan>.md`
- SDD 逐任务执行 + 逐任务审查 + fable 终审 + 修复闭环
- 提交推 Codeup；CLAUDE.md（端点/表/基线/挂账）+ README（功能矩阵）收尾同步
