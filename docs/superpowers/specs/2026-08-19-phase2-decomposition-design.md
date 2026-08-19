# 二期需求拆解设计（2026-08-19）

> 依据：`C:\Users\yuanmenglong\Desktop\AI数字员工架构及功能设计.md`（2026-08-17 修订版，老板已确认）
> 一期四计划（A 备案资质 / D 22 项映射 / B 医生端 / C 分享+简报）已于 2026-08-17 全部交付并推 Codeup。
> 本设计把二期（"加黏性，提升使用频次"，需求第八章）拆为 5 张可独立交付的实施计划（E/F/G/H/I），复用一期 SDD 流程。

## 1. 范围

二期共 18 项能力（管理后台 8 + 代表端 5 + 医生端 5），跨 4 个业务域，拆为 5 张计划。另含需求 4.3 三项一期未落地的分身管理能力（分身生成风格测试 / 分身风格设置 / 分身启停控制），归 H 计划（详见 §6）。

### 明确不进二期的三期边界

- 代表自有 Skill 发布/审核/下架/公共列表（skill_audits 审核流三期才启用代表侧）
- 患教专区内容审核流（edu_content_records.audit_status 三期启用）
- MAH 合规全景视图、数据分类分级、数据导出审批、医生隐私请求处理
- 第三方 CA 电子签（承诺书，二期仍为平台内电子确认）
- 国家备案平台自动校验接口（一期调研项，二期不接）
- 积分兑换加载 Skill（列为后续版本）

## 2. 通用决策

1. **分身 = `digital_specialists` 表**：一期已有 `doctor_twin_subscriptions`/`share_links`/`nightly_briefings` 均引用 `digital_specialists(id)`。二期迁移为 `digital_specialists` 新增列：
   - `representative_id BIGINT REFERENCES users(id)`（分身归属代表；官方公共数字员工为 NULL）
   - `is_official BOOLEAN NOT NULL DEFAULT FALSE`（官方公共数字员工标识）
   - `skill_package_id BIGINT`（内部引用 skill_packages，**任何 API 不返回**）
   - 不新建 `digital_twins` 表。
2. **新增表（分批迁移 013 起）**：
   - `skill_packages`：creator_id / is_public / is_anonymous / audit_status(pending/approved/rejected) / style_tags / heat / approval_rate / skill_weights(JSON，内容字段任何 API 不返回)
   - `skill_audits`：skill_id / auditor_id / audit_result / reason / created_at；审核人查看行为写平台访问审计
   - `training_materials`：标题 / 类型(办法/RDPAC/内部政策) / content / version
   - `exam_questions`：material_id / question_type(单选/多选/判断) / content / options(JSON) / answer / review_status(pending/approved/rejected) / reviewed_by
   - `exam_records`：representative_id / score / passed / submitted_at / commitment_signed_at
   - `academic_cards`：representative_id / content(JSON) / is_ai_generated / compliance_status / status
   - `card_push_records`：representative_id / doctor_id / card_id / read_status / read_at / feedback / created_at
   - `doctor_profiles`：doctor_id / interest_areas(JSON) / preferred_doc_type / preferred_style / updated_at
   - `patient_edu_templates`：disease_area / content / version / review_status / reviewed_by
   - `edu_content_records`：doctor_id / template_id / content / is_ai_generated / audit_status(pending/approved/rejected，三期启用) / visibility(private/shared)
3. **合规铁律贯穿**：AI 生成内容全部标注"AI 生成"；三层合规预检（学术卡片/陪练话术/AI 出题）走既有 `compliance /check`；引用无页码（以挂载元数据为准）；Skill 内容与权重任何 API 不返回、常规管理员不可见、仅审核人受控查看并留痕；权限走 `require_roles` 实时查库。
4. **流程**：每张计划 = 需求章节 → writing-plans 出 plan → SDD 逐任务执行 + 逐任务审查 + fable 终审 + 修复闭环 → 推 Codeup；CLAUDE.md / README 收尾同步。执行顺序 **F → E → G → H → I**。
5. **培训前置：先上线不强制**（已拍板）。考试系统上线后仅提示未完成，不限制使用；提供配置开关，政策确认后再强制。
6. **一期挂账并入**：简报真实推送/通知渠道（G）、医生端收藏与历史接线（I）、chat 订阅校验硬限制（I）、web 检索测试页（E）、briefings 网关转发测试（G）。
7. **`<user_content>` 定界转义为通用约束**：二期所有新增 LLM 调用（学术卡片生成/陪练对话/AI 出题/偏好学习/患教生成/简报）必须应用 `<user_content>` 定界（对齐一期 S7/M7 口径）；既有残余（如 visit follow_up）在 E 或 G 顺带加固。
8. **需求 4.3 分身生成/风格设置/启停控制一期未做**（现 digital_specialists 仅 admin 可建，无风格测试/启停/归属）。分身风格设置（4.3(2)）与分身启停控制（4.3(5)）归 H 计划；分身生成（4.3(1) 风格测试生成画像）列为 H 的前置小项或独立挂账，由 H 计划开头澄清。

## 3. 计划 E：合规风控深化（Web 管理后台，需求 3.2/3.5）

**目的**：把一期已有的三层拦截从"可用"升级为"运营可视化 + 人工裁决闭环"。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| 拦截聚合告警 | 3.2(3) | compliance 聚合日报接口（按天/按规则/按分身聚合 blocks+violations）+ 高危规则（R001/R002 等可配置）实时阈值告警；告警聚合，不逐条推送 |
| 待复核冻结流 | 3.2(3) | 分身拦截计数超阈值（24h≥N，合规部配置）标记"待复核"；待复核列表 + 人工确认冻结/解冻（冻结理由必填、写审计、操作记录存档）；不做自动冻结（语义误报/fail-closed 场景靠人工裁决） |
| 违规趋势分析 | 3.2(4) | 时间维度触发次数曲线 + 代表维度排名 + 敏感词维度频率（基于 compliance_blocks/violations 聚合） |
| 对话日志全文检索 | 3.2(1) | conversations 全文检索（代表/医生/分身/时间范围/命中敏感词筛选）+ 点击查看完整上下文；对话全文只落 conversations 表 |
| 分身状态监控与使用统计 | 3.5(1)(3) | digital_specialists 列表（今日服务量/平均响应时长/服务医生数/合规健康度绿黄红按 30 天拦截率分级）+ 被添加次数/日均对话量/好评率统计 |
| 官方公共数字员工管理 | 3.5(4) | is_official 分身 CRUD（医学部维护，供医生侧广场，状态监控与冻结规则同个人分身） |
| 陪练场景/异议话术库管理 | 3.2(5) | 管理端入口（场景/医生性格/异议话术由合规部创建与审核；话术版本管理留痕；H 计划建表，E 计划仅补管理页若依赖满足） |
| web 检索测试页 | 3.1(3) | 并入一期挂账：管理员输入查询词预览检索结果与引用来源（复用 knowledge /search-test） |

**边界**：不引入自动冻结；告警只聚合+高危实时，不逐条邮件。

## 4. 计划 F：培训考试 + 承诺书（需求 3.4 + 代表端 4.2(4)）

**目的**：满足《医药代表管理办法》合规培训前置与年度承诺书要求（先上线不强制）。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| 培训材料管理 | 3.4(1) | 内置《医药代表管理办法》全文 + RDPAC 准则（种子数据）+ 药企自定义上传（training_materials） |
| 题库与考试 | 3.4(2) | AI 出题（单选/多选/判断）→ 医学部/合规部人工复核后入库（review_status）；在线考试 + 80 分合格（可配置）+ 补考；exam_records |
| 培训记录存档 | 3.4(3) | 接线 representative_qualifications 的 compliance_training_completed / compliance_exam_score / commitment_signed 三字段（一期已建列未接线） |
| 年度承诺书签署 | 3.4(4) | 勾选 + 短信验证码 + 审计留痕（一期定）；二期可选第三方 CA（不做） |
| 代表端个人合规中心 | 4.2(4) | 培训学习 + 考试 + 承诺书签署 + 备案/合规记录聚合（复用一期 ComplianceCenter） |
| 培训前置（先上线不强制） | 七、数据隐私边界 | 提供状态查询与页面提示，不限制使用；配置开关预留 |

**边界**：不做强制门禁（已拍板）；不做第三方 CA 电子签。

## 5. 计划 G：学术触达（需求 4.6/5.3/6.3/3.7(1)）

**目的**：代表端生成学术卡片 → 推送医生 → 阅读追踪 → 反馈回流，形成代表—医生学术互动闭环。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| 学术卡片生成 | 4.6(1) | AI 生成（核心结论+关键数据带引用+一句话总结，标注"AI 生成"）；三层合规预检（复用 compliance /check，无需人工审核）；代表预览确认后发送；academic_cards |
| 推送与阅读追踪 | 4.6(2)(3) | 从通讯录（hcps/已添加医生）选择推送（card_push_records）；未读/已读/收藏/转发 + 停留时长；长时间未读提醒 |
| 医生端接收与反馈 | 5.3(1)(4) | 医生端消息中心收卡片（学术摘要形式、标注学术交流目的）；有用/无用 + 追问 |
| 反馈回流 | 6.3 | 有用 → 分身好评计数（同步管理后台统计）；追问 → 代表简报 + 实时通知 |
| 学术内容触达统计 | 3.7(1) | 点击人次/点击率 + 代表排名 + 治疗领域排名 |
| 简报真实推送/通知渠道 | 一期 C 挂账 | 站内信（nightly_briefings 状态 + 消息中心）+ 可选阿里云移动推送；代表端通知到达 |
| 顺带收尾 | 终审挂账 | briefings 网关转发测试；`<user_content>` 定界转义加固（既有残余，对齐 §2.7） |

**边界**：卡片内容合规预检为自动三层（无人工审核）；推送渠道一期仅站内信 + 可选推送 SDK，不接短信。

## 6. 计划 H：AI 陪练 + Skill 模版（需求 4.5/3.6(4)/4.7/3.2(5)）

**目的**：代表通过官方 Skill 模版驱动的 AI 陪练提升学术沟通能力；官方模版供给代表侧广场。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| 官方 Skill 模版管理 | 3.6(4) | 医学部创建官方模版（skill_packages，is_public + audit_status）；可直接下发陪练场；可上架广场；Skill 内容仅审核人受控查看（skill_audits + 访问审计） |
| 陪练场景库 | 3.2(5) | 科室/医生性格/产品场景 + 合规部审核的异议话术库；话术版本管理留痕 |
| AI 陪练 | 4.5 | 代表端选场景 + 加载官方 Skill 模版 → 3-5 轮多轮对话（AI 医生主动抛异议）→ 自动评分（循证引用准确度/异议应对流畅度/沟通逻辑性）+ 逐句反馈 + 练习记录存档 + 进步曲线 |
| 代表侧广场 | 4.7(1)(2)(3) | 按治疗领域浏览/搜索/排序（最新/最热/好评）；加载到陪练场；已加载标记；**只加载官方模版**（代表发布 Skill 为三期） |
| 分身挂 Skill | 附录 A | digital_specialists.skill_package_id 内部引用，任何 API 不返回 |
| 分身风格设置 | 4.3(2) | 正式程度（非常严谨/标准学术/略带亲和力）+ 回复长度（简洁/标准/详尽）+ 开场白模式（直切主题/先寒暄）；写入 persona；影响分身对话风格与陪练评分 |
| 分身启停控制 | 4.3(5) | 代表可暂停/启用本人分身（digital_specialists.status）；暂停后对外对话不可用 |
| 分身生成（前置小项） | 4.3(1) | 一期未做（现仅 admin 建分身）。H 计划开头澄清：以"风格测试 5 题 + 既有 persona 更新"轻量实现，不做微调模型（对齐附录 B-10 prompt/检索级个性化） |

**边界**：代表个人 Skill 发布/审核/下架（三期）；积分兑换加载（后续版本）；广场仅官方模版供给。

## 7. 计划 I：医生端体验（需求 5.4/5.5/5.6/3.9(2)/3.7(2)(3)）

**目的**：医生端从"可用"升级为"懂医生的个性化助手"；患教模板库 + 医生侧官方广场补齐医生侧内容。

| 功能 | 需求点 | 实现要点 |
|---|---|---|
| 学术偏好引擎 | 5.4(1)(3) | 自动学习文献类型/疾病领域/回复长度偏好（doctor_profiles）；偏好查看修改；可完全关闭个性化 |
| 个性化学术简报 | 5.4(2) | 每周自动生成（基于偏好筛选内容），医生端查看 |
| 医生侧公共广场 | 5.6 | 按科室浏览官方公共数字员工（is_official）；快速添加（添加前知情同意：对话同步至平台合规审计）；热门排行（被添加 Top10/好评 Top10） |
| 智能患教工具（模板版） | 5.5 | 预审模板微调（patient_edu_templates + edu_content_records）；AI 生成图文卡片（通俗语言+注意事项+就医指征）；标注"AI 生成"默认仅本人可见；转发前弹窗确认；**不采集患者诊断/用药** |
| 患教模板库管理 | 3.9(2) | 医学部创建/审核患教模板；版本管理留痕 |
| 运营统计 | 3.7(2)(3) | 医生活跃度（日活/周活/月活）+ 数字分身使用排行（服务医生数 Top10/好评率 Top10/合规健康度排名） |
| 医生端收藏与历史接线 | 5.2(4) 一期 B 挂账 | 复用 specialist 收藏端点，医生端历史问答/收藏页面接线 |
| chat 订阅校验硬限制 | 一期 B 挂账 | 未订阅（doctor_twin_subscriptions）不可 chat |

**边界**：患教专区审核流（三期）；医生隐私请求处理（三期）；医生端流式对话（一期 B 挂账，二期仍可挂账或顺带接）。

## 8. 依赖与执行顺序

```
F 培训考试 ──► E 合规风控 ──► G 学术触达 ──► H AI陪练+Skill ──► I 医生端体验
  (独立性强)    (独立)        (复用简报/分享)  (依赖 Skill 建表)   (依赖 is_official + 偏好积累)
```

- **F**：无前置依赖，合规刚需，先做。
- **E**：无前置依赖（alerts/趋势基于既有 compliance_blocks/violations）；is_official 字段在 E 引入，H/I 复用。
- **G**：复用一期 share_links/nightly_briefings；卡片推送依赖医生端已有消息入口（B 计划基础）。
- **H**：依赖 skill_packages/skill_audits 新建 + digital_specialists 分身管理改造（无外部依赖，可与 E 并行）。
- **I**：依赖 digital_specialists.is_official（E 引入）、doctor_profiles（本计划建）、患教模板库（本计划建）。

## 9. 风险与注意

- `digital_specialists` 新增列是公开契约变更，specialist-service 序列化需显式排除 `skill_package_id`，避免泄漏。
- 考试/AI 出题内容必须人工复核后入库（AI 直接可用质量无法保证，需求明确）。
- 陪练评分依赖既有引用溯源（citations），需确认 specialist 对话引用在陪练场景可用。
- 学术卡片合规预检走自动三层；若命中拦截，卡片创建应 fail-closed 丢弃并提示。
- 推送渠道决策（站内信 vs 推送 SDK）在 G 计划编写时再定；站内信零依赖，推送 SDK 需新增依赖。
- 每张计划保持一期验证门：后端 pytest 全量 + mobile jest + web build + 移动端 assembleDebug。

## 10. 交付产物

每张计划（E/F/G/H/I）独立：
- 实施计划文档 `docs/superpowers/plans/2026-08-19-<plan>.md`
- SDD 逐任务执行 + 逐任务审查 + fable 终审 + 修复闭环
- 提交推 Codeup；CLAUDE.md（端点/表/基线/挂账）+ README（功能矩阵）收尾同步
