# 数字员工系统 开发实施手册

> 项目代号：MedAgent
> 文档用途：开发实施手册，团队照着做
> 版本：v4.0 · 2026-07-31

---

## 目录

- 第 1 章 · 我们要做什么产品
- 第 2 章 · 功能清单
- 第 3 章 · UI 界面设计
- 第 4 章 · 技术架构
- 第 5 章 · 环境搭建
- 第 6 章 · 数据模型
- 第 7 章 · API 设计规范
- 第 8 章 · 核心模块开发
- 第 9 章 · AI 能力实现
- 第 10 章 · 合规审核实现
- 第 11 章 · 移动端开发
- 第 12 章 · 知识库构建
- 第 13 章 · 代码规范
- 第 14 章 · 测试规范
- 第 15 章 · 部署上线
- 附录 · 目录结构与命名

---

# 1. 我们要做什么产品

## 1.1 产品是什么

数字员工系统是一套面向医药代表日常工作场景的智能助手系统。简单说，就是**给每个代表配一个懂产品、懂医生、懂合规的随身数字专员**。

它不是一个 ChatGPT 套壳，而是一个完整的数字员工操作系统，包含数字专员、陪访助手、知识库、合规审核、审计系统等模块。

## 1.2 解决什么问题

医药代表日常有三个最头疼的问题：

第一个是现场答不上专业问题。医生临时问"这药和 XX 区别"、"剂量怎么调"、"不良反应怎么处理"，答不上来很尴尬，回去查半天，下次再问可能忘了。数字专员的解决方案是 24 小时在线回答，3 秒内有答案加文献来源。

第二个是拜访完要写半小时记录。见完医生要记聊了什么、医生什么反应、下次注意什么，现场记不全，回去补要 30 分钟。陪访助手的解决方案是拜访时自动转写，1 分钟自动生成结构化记录。

第三个是说错话担合规风险。不知道哪句话违规，监管来查没有证据。合规审核的解决方案是实时拦截违规话术，所有对话有审计日志。

## 1.3 谁会用

- 医药代表（50%）：移动端 App，核心用户
- 市场部（15%）：Web 后台、内容平台
- 医学顾问（10%）：数字专员、知识库
- 合规/法务（5%）：Web 后台，合规规则、审计查询
- 管理者（5%）：Web 后台，驾驶舱
- 系统管理员（7%）：Web 后台，用户管理、系统配置
- 其他（8%）：财务、运营等

## 1.4 关键场景示例

### 场景 A：代表上午见 3 个医生

早上 7 点半，代表打开 App 工作台，看到今天 3 位医生的准备包。每位医生都有画像、推荐话题、红线提醒。

8 点开始拜访医生 A，按下录音按钮。医生说"这药比 XX 好吗"，App 立即弹出文献证据。医生问"价格贵不少"，App 识别出价格异议，弹出应对话术建议。

8 点半拜访结束，App 自动生成拜访记录。代表花 1 分钟确认关键点、跟进事项，提交完成。

9 点拜访医生 B，临时想查"剂量怎么调"，直接打开数字专员对话。3 秒后得到答案，附说明书引用。

10 点拜访医生 C，代表想说某句话，App 检测到违规，立即弹出警告，代表改用合规话术。

11 点全部拜访完成，工作台显示今日完成度。

### 场景 B：医学顾问做学术支持

MSL 在 Web 后台上传一份新发表的临床研究。文档进入待审核状态，医学顾问审核通过后，自动向量化入库。代表下次提问相关问题时就能引用到。

### 场景 C：合规部门飞行检查

监管通知下周二来查 Q2 代表拜访记录。合规人员打开 Web 后台审计模块，筛选时间范围，一键导出 Excel 报告，含所有 AI 决策日志、合规检查记录，监管顺利通过。

---

# 2. 功能清单

## 2.1 优先级总览

P0（必做）模块：
- 数字学术专员：每产品一个 AI 专员、学术问答、陪访助手
- 知识库：产品资料、临床文献、指南、法规
- 合规审核：违规话术实时拦截、规则可热更新
- 审计留痕：所有操作有日志、可导出报告

P1（第二版）模块：
- 医生/专家管理：医生档案、互动历史、标签管理
- 决策驾驶舱：业务总览、风险热力图
- 学术内容：内容上传、分发、效果追踪

P2（后续）模块：
- 会议活动：学术活动全流程管理
- 费用支付：预算、HCP 付款合规
- 医生行为模拟：AI 扮演医生做培训和预演

第一版要实现的：P0 的 4 个模块，加上 P1 的医生/专家管理（简化版）。

## 2.2 各模块功能详解

### 2.2.1 数字学术专员（核心模块）

这是整个系统最核心的模块。

专员列表：代表能看到所有可用的数字专员（按产品分）。这是必做项。

与专员对话：输入问题，3 秒内得到答案加文献来源。这是必做项。

多轮对话：支持上下文连续提问，必做。

引用溯源：每个回答都附文献来源，可点击查看，必做。

证据等级：答案标注证据等级（A/B/C/专家共识/未知），必做。

反馈：代表可对回答点赞点踩，反馈质量问题，必做。

收藏：代表可收藏常用问答，必做。

专员配置：管理员可创建、编辑、停用专员，必做。

专员人设：每个专员有沟通风格（专业/亲和/学术），后续版本。

多专员协同：多个产品专员协同回答跨产品问题，后续版本。

专员数据看板：管理员查看每个专员的使用量、满意度，必做。

### 2.2.2 陪访助手

代表每天都在用的功能。

拜访前：
- 医生画像（学历、处方偏好、学术倾向），必做
- 历史互动摘要（上次聊了什么、跟进事项），必做
- 推荐话题，3-5 个基于医生兴趣的话题，必做
- 红线提醒（该医生关注什么禁区、近期投诉），必做
- 开场白建议，AI 生成的开场白，必做
- 资料包，一键打包本次拜访可能用到的材料，后续版本

拜访中：
- 实时转写，语音转文字（双方分离），延迟小于 2 秒，必做
- 异议识别，识别医生异议并提示，必做
- 话术建议，实时推荐应对话术，后续版本
- 红线拦截，代表想说的话不合规时立即拦截，必做
- 关键节点标记，AI 自动标记"决策点"、"兴趣点"，后续版本

拜访后：
- 自动生成记录，1 分钟生成结构化拜访记录，必做
- 关键点提取，自动提取关键讨论点，必做
- 跟进建议，推荐下次拜访时间加话题，必做
- 任务创建，自动创建后续任务（送资料、约时间），必做
- 推送内容，给医生推送个性化学术内容，后续版本
- 医生画像更新，基于本次拜访更新医生画像，必做

### 2.2.3 知识库

整个 AI 能力的基础。

文档上传：支持 PDF、Word、PPT、TXT，必做。

自动解析：表格识别、图片 OCR、章节识别，必做。

智能切分：按章节/段落/语义切分，必做。

向量化：自动嵌入到 DashVector，必做。

关键词索引：全文索引（Elasticsearch），必做。

混合检索：向量加关键词混合检索，必做。

精排：检索结果重排，必做。

文档审核流：上架前必须医学顾问审核，必做。

版本管理：文档多版本管理，必做。

过期提醒：知识过时自动告警，后续版本。

知识图谱：实体-关系-证据结构化，后续版本。

知识检索测试：管理员可在线测试检索效果，必做。

用户反馈：用户对检索结果可反馈，必做。

### 2.2.4 合规审核

系统的生死线。

关键词规则：关键词匹配拦截，必做。

正则规则：正则表达式模式，必做。

语义审核：用 AI 理解语义，识别复杂违规，必做。

规则热更新：规则可热更新无需重启，必做。

规则分级：高中低三级严重程度，必做。

拦截动作：reject（拒绝）、warn（警告）、log（仅记录），必做。

拦截记录：所有拦截有日志，必做。

规则测试：管理员可在线测试规则，必做。

监管自查报告：一键导出含所有 AI 决策的合规报告，必做。

监管政策跟踪：NMPA/医保政策自动监控，后续版本。

### 2.2.5 审计留痕

监管合规必须。

全量操作日志：所有用户操作都记录，必做。

AI 决策日志：所有 AI 生成的答案都记录，必做。

不可篡改：审计日志不可修改、不可删除，必做。

高级搜索：按时间、用户、操作类型搜索，必做。

监管报告导出：一键导出 Excel 格式报告，必做。

统计图表：操作量、拦截率、活跃度等，必做。

### 2.2.6 医生/专家管理（第二版）

医生列表：列表展示、搜索、筛选，必做。

医生详情：完整档案，基本信息、学术背景、处方偏好，必做。

互动历史：与代表的所有互动记录，必做。

标签管理：灵活打标签，必做。

画像自动更新：基于拜访自动更新画像，后续版本。

批量导入：从 Excel/飞书批量导入，必做。

飞书同步：与飞书表格双向同步，必做。

影响网络：医生影响网络分析，后续版本。

### 2.2.7 决策驾驶舱（第二版）

业务总览：关键指标卡片，必做。

使用趋势：日/周/月趋势图，必做。

风险热力图：各区域/代表/产品的风险分布，必做。

实时动态：当前在线用户、活跃对话，必做。

决策建议：AI 给出"建议关注 X 区域"，后续版本。

自定义看板：拖拽自定义图表，后续版本。

---

# 3. UI 界面设计

本章详细说明所有 UI 板块，每个板块的目的、核心内容、关键交互。

## 3.1 移动端 UI（代表用，React Native）

### 3.1.1 移动端整体结构

移动端底部有 4 个 Tab：
- 工作台：今日工作总览
- 对话：数字专员对话
- 医生：医生档案管理
- 我的：个人中心

### 3.1.2 登录页

目的：身份认证，确保只有授权代表能使用系统。

核心内容：
- Logo（MedAgent 标识）
- 手机号输入框
- 验证码输入框和获取按钮
- 登录按钮
- 协议勾选

关键交互：
- 输入手机号自动校验格式
- 60 秒倒计时后才能重发验证码
- 登录成功后跳到工作台

### 3.1.3 工作台

目的：代表每天打开 App 第一眼看到的页面，今日工作一目了然。

核心内容：

顶部欢迎栏：日期、天气、通知、设置入口。

今日进度：今日拜访完成度（X/Y 形式）。

今日拜访列表：按时间排序的医生列表。每张卡片包含医生姓名、医院、时间、状态（已完成/待开始/进行中）。已完成显示完成时间，待开始显示"准备包"按钮。

添加拜访：手动添加临时拜访。

快捷功能：问答、内容、医生 3 个常用入口。

各板块的目的：

医生卡片让代表一眼看清今天要见谁、几点、是否准备好了。完成时间标记方便复盘时间管理。优先级标记（用"高优"文字而非表情）提醒哪些医生重要。

### 3.1.4 拜访前准备页

目的：拜访前 5 到 10 分钟快速了解医生、准备话题、避免踩雷。

核心内容：

医生基本信息：医院、科室、职称。

医生画像：AI 分析的学术背景、处方偏好、沟通风格。

推荐话题：3-5 个 AI 推荐的话题（可勾选/编辑）。

红线提醒：绝对不能说的话，最关键的部分。

开场白建议：AI 生成的开场白，可直接用或改。

资料包：本次拜访可用的资料。

上次跟进：上次的讨论要点加承诺事项。

开始拜访按钮：进入拜访中。

各板块的目的：

医生画像让代表快速了解对方是什么样的人。推荐话题避免冷场，每次拜访都有重点。红线提醒是合规底线，避免说错话。开场白建议降低拜访开头难度。资料包需要时直接调出。上次跟进避免重复上次的内容，体现专业性。

### 3.1.5 拜访中

目的：拜访过程中实时辅助代表，像副驾一样提示。

核心内容：

顶部状态：录音中、时长。

实时转写区：医生/代表对话分离显示。

实时提示区（核心）：
- 异议识别
- 话术建议
- 引用资料快捷发送

关键节点标记：自动加手动。

结束拜访按钮。

各板块的目的：

实时转写避免记不全，事后有据可查。异议识别让医生不满意的瞬间立即提示。话术建议让代表有备选应对方案。引用资料可现场调出证据增强说服力。关键节点标记方便事后回看。

关键交互：
- 转写延迟小于 2 秒
- 提示卡片可展开/收起
- 长按提示卡片可固定显示

### 3.1.6 拜访后

目的：1 分钟完成拜访记录，不用再花半小时写报告。

核心内容：

AI 摘要：100 字以内的拜访总结。

关键点：本次讨论的核心要点。

医生兴趣点：可以深入的方向。

医生异议：需要后续处理的问题。

情感判断：积极/中性/消极。

下次拜访时间：AI 推荐。

推荐话题：下次聊什么。

自动任务：可以一键执行（发送资料、预约等）。

各板块的目的：

AI 摘要让代表 5 秒了解本次拜访。关键点避免遗忘重要内容。兴趣点和异议为下次拜访准备。情感判断用于判断关系是否健康。跟进建议让代表知道下一步做什么。自动任务减少手动操作。

关键交互：
- 每个模块可编辑
- 一键"确认完成"提交
- 可分享给上级

### 3.1.7 数字专员对话页

目的：代表随时向数字专员提问，3 秒内有答案。

核心内容：

顶部专员名：当前对话的专员。

对话流：
- 代表消息（右对齐）
- 专员消息（左对齐）
- 引用来源卡片
- 证据等级标注
- 反馈、收藏、分享按钮

输入区：文本输入、语音输入、发送。

各板块的目的：

对话流支持连续多轮对话。引用来源让所有结论可溯源。证据等级让代表知道这个答案的可信度。反馈按钮用于收集代表意见，持续优化。收藏功能用于常用问答方便查找。分享功能可分享给同事或医生。

关键交互：
- 支持多轮对话
- 语音输入自动转文字
- 长按消息可复制/反馈

### 3.1.8 数字专员列表页

目的：让代表选择要咨询的专员。

核心内容：每个产品专员一张卡片，显示状态、回答次数。点击进入对话。

### 3.1.9 医生档案页

目的：查看医生的完整信息。

核心内容：

医生基本信息：姓名、医院、科室、职称、联系方式。

快捷操作：打电话、发消息、预约。

学术背景：教育、任职、研究方向。

处方偏好：基于历史拜访分析的偏好。

标签：灵活标签。

互动历史：所有拜访记录。

各板块的目的：

基本信息让人知道对方是谁。学术背景便于找共同话题。处方偏好用于精准推荐产品。互动历史便于了解关系进展。

### 3.1.10 医生搜索页

目的：快速找到医生。

核心内容：
- 搜索框（姓名/医院/科室）
- 快速筛选（医院、科室、标签）
- 最近浏览
- 我的医生
- 字母索引

### 3.1.11 学术内容页

目的：查看学习学术资料。

核心内容：
- 分类导航（指南/文献/产品/病例/视频/合规）
- 推荐内容
- 最新内容
- 搜索

### 3.1.12 我的

目的：个人信息和设置。

核心内容：
- 个人信息（姓名、职位、区域）
- 统计概览（对话数、拜访数、收藏数）
- 功能入口（个人资料、团队、统计、通知、帮助、合规手册）
- 退出登录

### 3.1.13 合规手册页

目的：随时查看合规规则，避免说错话。

核心内容：
- 红线清单：明确不能说的话
- 错误 vs 正确对比：让代表知道怎么改
- 联系方式：遇到问题能找到人

各板块的目的：

红线清单让代表明确底线。错误与正确对比让代表知道怎么改。联系方式用于遇到问题能找到人。

## 3.2 Web 后台 UI（管理员用）

### 3.2.1 Web 整体结构

左侧菜单包含：仪表盘、数字专员、知识库、医生、合规、审计、系统。

### 3.2.2 仪表盘

目的：管理者第一眼看到业务总览。

核心内容：

关键指标卡片：活跃用户、对话量、违规率、满意度。

使用趋势图：对话量随时间变化。

风险热力图：各区域/代表风险分布。

合规拦截 Top：最常见的违规话术。

实时动态：当前系统活动。

### 3.2.3 数字专员管理

目的：管理所有数字专员。

专员列表：显示每个专员的状态、今日使用量、满意度。

筛选/搜索：按产品、状态筛选。

创建/编辑专员：
- 基本信息：名称、关联产品、百炼 App ID
- 能力配置：知识范围、合规等级
- 人设：沟通风格、自我介绍
- 话术模板：编辑话术 YAML
- 状态：草稿/实习/正式/停用

数据查看：每个专员的使用统计、用户反馈。

### 3.2.4 知识库管理

目的：管理知识库内容。

统计：文档数量、标签数量、chunk 数量。

筛选：按类型、状态、产品筛选。

文档列表：每条显示标题、类型、状态、日期。

上传文档：
- 拖拽文件或选择文件（支持 PDF/Word/PPT/TXT）
- 文档信息：标题、类型、关联产品、证据等级、来源、发布日期
- 处理选项：自动解析、提交审核

检索测试：输入问题测试检索效果，可反馈。

### 3.2.5 合规规则管理

目的：维护合规规则。

规则统计：启用规则数、拦截次数、拦截率。

规则列表：每条规则显示编码、名称、类型、严重程度、模式、拦截次数。

新增/编辑规则：
- 规则编码、名称
- 规则类型：关键词/正则/语义
- 严重程度：高/中/低
- 触发动作：拒绝/警告/仅记录
- 匹配模式
- 描述

规则测试：输入测试内容，查看是否命中。

拦截记录：所有拦截的详细记录。

### 3.2.6 审计查询

目的：查询所有操作记录，监管合规。

高级搜索：时间范围、用户、服务、操作类型、风险等级。

统计：总记录数、命中规则数。

日志列表：每条显示时间、服务、用户、操作、风险等级。

详情：查看具体内容。

监管报告导出：一键导出 Excel 格式报告。

### 3.2.7 医生/专家管理

目的：管理医生档案。

搜索和筛选。

医生列表：显示姓名、医院、职称、标签、拜访次数、满意度。

医生详情：完整档案。

### 3.2.8 用户管理

目的：管理系统用户。

角色筛选：管理员、管理者、代表、合规、医学、财务。

用户列表：显示姓名、电话、角色、区域、状态。

新增/编辑用户。

角色说明：每个角色的权限说明。

### 3.2.9 系统配置

目的：系统级配置。

阿里云配置：
- Account ID
- 区域
- 百炼 App ID
- 通义千问 API Key
- 通义听悟

通知配置：合规拦截通知、系统异常通知、通知接收人。

日志配置：日志保留天数、审计日志不可删除。

---

# 4. 技术架构

## 4.1 整体架构（5 层）

```
+--------------------------------------------------+
| 1. 接入层                                        |
|   移动 App (React Native) | Web 后台 | IM 集成  |
+--------------------------------------------------+
                       |
+--------------------------------------------------+
| 2. 网关层                                        |
|   阿里云 API 网关 / Nginx - 限流/认证/路由       |
+--------------------------------------------------+
                       |
+--------------------------------------------------+
| 3. 应用层（6 个微服务）                          |
|   specialist | visit | knowledge | compliance  |
|   | audit | hcp                                 |
+--------------------------------------------------+
                       |
+--------------------------------------------------+
| 4. 系统能力层                                    |
|   阿里云百炼 + 通义千问 + 通义听悟 + Qwen-VL    |
+--------------------------------------------------+
                       |
+--------------------------------------------------+
| 5. 数据 & 基础设施层                             |
|   RDS PostgreSQL | Redis | OSS | DashVector    |
+--------------------------------------------------+

合规审核 + 审计 = 横切所有业务（独立部署）
```

## 4.2 技术选型

| 层 | 选型 | 用途 |
|---|------|------|
| 大模型 | 通义千问 Qwen-Max/Plus/Turbo | 文本生成、推理 |
| 多模态 | 通义千问 VL | 图像理解、文献截图 |
| 语音 | 通义听悟 | ASR、TTS |
| 业务编排 | 阿里云百炼 | 专员配置、知识检索、话术管理 |
| 向量检索 | 阿里云 DashVector | 知识库语义检索 |
| 后端 | Python FastAPI | AI 业务接口 |
| 数据库 | 阿里云 RDS PostgreSQL + Redis | 主数据 + 缓存 |
| 对象存储 | 阿里云 OSS | 文档、图片 |
| Web 前端 | React + Ant Design Pro | Web 后台 |
| 移动端 | React Native | iOS + Android |
| 监控 | 阿里云 ARMS / SLS | 性能监控、日志 |
| CI/CD | 阿里云云效 | 持续集成、部署 |

## 4.3 微服务清单

| 服务名 | 职责 | 端口 |
|--------|------|------|
| specialist-service | 数字学术专员（核心） | 8001 |
| visit-service | 陪访助手 | 8002 |
| knowledge-service | 知识库（底座） | 8003 |
| compliance-service | 合规审核（独立） | 8004 |
| audit-service | 审计服务 | 8005 |
| hcp-service | 医生/专家合作 | 8006 |
| gateway | API 网关 | 8000 |

## 4.4 项目仓库结构

```
medagent/
├── services/                  # 微服务代码
│   ├── specialist-service/
│   ├── visit-service/
│   ├── knowledge-service/
│   ├── compliance-service/
│   ├── audit-service/
│   ├── hcp-service/
│   └── gateway/
├── mobile/                    # React Native App
├── web/                       # Web 后台
├── shared/                    # 共享代码
│   ├── common/                # 通用工具
│   ├── models/                # 数据模型
│   ├── prompts/               # 话术模板
│   └── compliance-rules/      # 合规规则
├── knowledge-base/            # 知识库原始资料
├── scripts/                   # 运维脚本
├── docs/                      # 文档
└── docker-compose.yml         # 本地开发编排
```

---

# 5. 环境搭建

## 5.1 阿里云账号信息（团队共享）

```
阿里云账号：13523341069
登录方式：手机号 + 短信验证码
已开通服务：
  - 阿里云百炼 (bailian.console.aliyun.com)
  - 通义千问 API (通过百炼调用)
  - 通义听悟 (tingwu.console.aliyun.com)
  - 阿里云 DashVector
  - 阿里云 RDS PostgreSQL
  - 阿里云 Redis
  - 阿里云 OSS
  - 阿里云 API 网关
  - 阿里云 ARMS 监控
  - 阿里云 SLS 日志
```

AccessKey 获取：
- 登录阿里云控制台
- 右上角头像 → AccessKey 管理
- 创建 AccessKey，记录 ID 和 Secret 到团队密码管理工具

百炼平台地址：https://bailian.console.aliyun.com/，已开通，直接用账号登录。

## 5.2 本地开发环境

```bash
# 1. 安装 Python 3.11+
python --version

# 2. 安装 Node.js 18+
node --version
npm --version

# 3. 安装 Docker Desktop
docker --version
docker-compose --version

# 4. 安装 React Native CLI
npm install -g react-native-cli

# 5. 克隆项目
git clone https://git.example.com/medagent.git
cd medagent

# 6. 复制环境变量模板
cp .env.example .env
# 填入阿里云 AccessKey、API Key 等
```

## 5.3 环境变量配置

`.env` 文件：

```bash
# 阿里云账号（团队共享）
ALIYUN_ACCESS_KEY_ID=your_access_key
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret
ALIYUN_REGION=cn-hangzhou

# 通义千问 API（通过百炼平台）
DASHSCOPE_API_KEY=your_dashscope_api_key
QWEN_MAX_MODEL=qwen-max
QWEN_PLUS_MODEL=qwen-plus
QWEN_TURBO_MODEL=qwen-turbo
QWEN_VL_MODEL=qwen-vl-max

# 通义听悟
TINGWU_APP_KEY=your_tingwu_app_key
TINGWU_ACCESS_TOKEN=your_tingwu_token

# 阿里云百炼
BAILIAN_APP_ID=your_bailian_app_id
BAILIAN_API_KEY=your_bailian_api_key

# 阿里云 DashVector
DASHVECTOR_API_KEY=your_dashvector_api_key
DASHVECTOR_ENDPOINT=your_endpoint

# 阿里云 OSS
OSS_ACCESS_KEY_ID=your_oss_key
OSS_ACCESS_KEY_SECRET=your_oss_secret
OSS_BUCKET=medagent-files
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com

# 数据库
DATABASE_URL=postgresql://user:pass@host:5432/medagent
REDIS_URL=redis://host:6379/0

# JWT
JWT_SECRET=your_jwt_secret
JWT_EXPIRES_IN=7d

# 服务端口
SPECIALIST_SERVICE_PORT=8001
VISIT_SERVICE_PORT=8002
KNOWLEDGE_SERVICE_PORT=8003
COMPLIANCE_SERVICE_PORT=8004
AUDIT_SERVICE_PORT=8005
HCP_SERVICE_PORT=8006
GATEWAY_PORT=8000
```

## 5.4 Docker 本地环境

`docker-compose.yml`：

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: medagent
      POSTGRES_USER: medagent
      POSTGRES_PASSWORD: medagent123
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init_db.sql:/docker-entrypoint-initdb.d/init.sql

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  specialist-service:
    build: ./services/specialist-service
    ports:
      - "8001:8001"
    env_file: .env
    depends_on:
      - postgres
      - redis

  visit-service:
    build: ./services/visit-service
    ports:
      - "8002:8002"
    env_file: .env
    depends_on:
      - postgres
      - redis

  knowledge-service:
    build: ./services/knowledge-service
    ports:
      - "8003:8003"
    env_file: .env
    depends_on:
      - postgres
      - redis

  compliance-service:
    build: ./services/compliance-service
    ports:
      - "8004:8004"
    env_file: .env
    depends_on:
      - postgres
      - redis

  audit-service:
    build: ./services/audit-service
    ports:
      - "8005:8005"
    env_file: .env
    depends_on:
      - postgres

  hcp-service:
    build: ./services/hcp-service
    ports:
      - "8006:8006"
    env_file: .env
    depends_on:
      - postgres

volumes:
  postgres_data:
  redis_data:
```

启动：

```bash
docker-compose up -d

# 查看日志
docker-compose logs -f specialist-service

# 停止
docker-compose down
```

## 5.5 验证环境

```bash
# 健康检查
curl http://localhost:8001/health
# 期望返回：{"status": "ok", "service": "specialist-service"}

# 调通义千问 API 测试
python -c "
from openai import OpenAI
client = OpenAI(
    api_key='your-dashscope-api-key',
    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1'
)
response = client.chat.completions.create(
    model='qwen-max',
    messages=[{'role': 'user', 'content': '你好'}]
)
print(response.choices[0].message.content)
"

# 调百炼 API 测试
python -c "
import requests
headers = {'Authorization': f'Bearer {YOUR_BAILIAN_API_KEY}'}
response = requests.get('https://bailian.aliyuncs.com/v2/app/list', headers=headers)
print(response.json())
"
```

---

# 6. 数据模型

## 6.1 核心实体关系图

```
Product  --<  ProductDetail
   |
   |
   v
DigitalSpecialist  -- N:M --  HCP
   |                    |
   |                    |
   v                    v
Conversation        VisitRecord
   |                    |
   v                    v
AuditLog  (统一审计)
```

## 6.2 数据库表设计（PostgreSQL）

```sql
-- 1. 用户表
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(100),
    role VARCHAR(20) NOT NULL,
    region VARCHAR(50),
    manager_id BIGINT REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_manager ON users(manager_id);

-- 2. 产品表
CREATE TABLE products (
    id BIGSERIAL PRIMARY KEY,
    product_code VARCHAR(50) UNIQUE NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    generic_name VARCHAR(200),
    manufacturer VARCHAR(200),
    indication TEXT,
    approval_date DATE,
    status VARCHAR(20) DEFAULT 'active',
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3. 数字专员表
CREATE TABLE digital_specialists (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    product_id BIGINT REFERENCES products(id),
    persona JSONB,
    knowledge_scope JSONB,
    compliance_level VARCHAR(20) DEFAULT 'internal',
    bailian_app_id VARCHAR(100),
    prompt_version VARCHAR(20),
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_specialists_product ON digital_specialists(product_id);
CREATE INDEX idx_specialists_status ON digital_specialists(status);

-- 4. 医生档案表
CREATE TABLE hcps (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    hospital VARCHAR(200),
    department VARCHAR(100),
    title VARCHAR(50),
    specialty VARCHAR(100),
    phone VARCHAR(20),
    email VARCHAR(100),
    region VARCHAR(50),
    academic_background JSONB,
    prescription_preference JSONB,
    influence_level VARCHAR(20),
    tags JSONB,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_hcps_hospital ON hcps(hospital);
CREATE INDEX idx_hcps_department ON hcps(department);
CREATE INDEX idx_hcps_region ON hcps(region);

-- 5. 拜访记录表
CREATE TABLE visit_records (
    id BIGSERIAL PRIMARY KEY,
    hcp_id BIGINT REFERENCES hcps(id),
    user_id BIGINT REFERENCES users(id),
    product_id BIGINT REFERENCES products(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),
    visit_time TIMESTAMP NOT NULL,
    duration_minutes INT,
    conversation_transcript TEXT,
    ai_summary TEXT,
    key_points JSONB,
    hcp_interests JSONB,
    hcp_objections JSONB,
    follow_up_suggestions JSONB,
    sentiment VARCHAR(20),
    compliance_flags JSONB,
    next_visit_plan JSONB,
    attachments JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_visits_hcp ON visit_records(hcp_id);
CREATE INDEX idx_visits_user ON visit_records(user_id);
CREATE INDEX idx_visits_time ON visit_records(visit_time);

-- 6. 对话记录表
CREATE TABLE conversations (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),
    session_id VARCHAR(100),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    citations JSONB,
    compliance_result JSONB,
    tokens_used INT,
    latency_ms INT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_conversations_session ON conversations(session_id);
CREATE INDEX idx_conversations_created ON conversations(created_at);

-- 7. 知识库文档表
CREATE TABLE knowledge_documents (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    doc_type VARCHAR(50) NOT NULL,
    source VARCHAR(200),
    content TEXT,
    file_url VARCHAR(500),
    product_id BIGINT REFERENCES products(id),
    evidence_level VARCHAR(20),
    publish_date DATE,
    version VARCHAR(20),
    status VARCHAR(20) DEFAULT 'draft',
    reviewer_id BIGINT REFERENCES users(id),
    review_date TIMESTAMP,
    tags JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_knowledge_type ON knowledge_documents(doc_type);
CREATE INDEX idx_knowledge_product ON knowledge_documents(product_id);
CREATE INDEX idx_knowledge_status ON knowledge_documents(status);

-- 8. 审计日志表（不可篡改）
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    service_name VARCHAR(50) NOT NULL,
    user_id BIGINT REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    before_value JSONB,
    after_value JSONB,
    ai_involved BOOLEAN DEFAULT FALSE,
    ai_model VARCHAR(50),
    ai_prompt_hash VARCHAR(100),
    ai_response_hash VARCHAR(100),
    compliance_result JSONB,
    risk_level VARCHAR(20),
    client_ip VARCHAR(50),
    user_agent TEXT,
    request_id VARCHAR(100)
);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_service ON audit_logs(service_name);
CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_action ON audit_logs(action);
REVOKE UPDATE, DELETE ON audit_logs FROM medagent;

-- 9. 合规规则表
CREATE TABLE compliance_rules (
    id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(50) UNIQUE NOT NULL,
    rule_name VARCHAR(200) NOT NULL,
    rule_type VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    severity VARCHAR(20) DEFAULT 'high',
    action VARCHAR(20) DEFAULT 'reject',
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    version INT DEFAULT 1,
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_compliance_enabled ON compliance_rules(enabled);

-- 10. 合规拦截记录表
CREATE TABLE compliance_blocks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    service_name VARCHAR(50),
    content TEXT,
    rule_code VARCHAR(50),
    rule_name VARCHAR(200),
    severity VARCHAR(20),
    action VARCHAR(20),
    context JSONB,
    blocked_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_compliance_blocks_user ON compliance_blocks(user_id);
CREATE INDEX idx_compliance_blocks_time ON compliance_blocks(blocked_at);
```

---

# 7. API 设计规范

## 7.1 通用规范

协议：HTTP/HTTPS
数据格式：JSON
字符编码：UTF-8
认证方式：JWT Token（放在 Authorization Header）
API 前缀：/api/v1/
请求 ID：每个请求带 X-Request-ID（UUID），用于链路追踪

## 7.2 通用响应格式

成功：

```json
{
  "code": 0,
  "message": "success",
  "data": { }
}
```

错误：

```json
{
  "code": 4001,
  "message": "问题包含敏感内容，已被合规系统拦截",
  "data": { "rule_code": "R001", "rule_name": "禁止承诺疗效" }
}
```

## 7.3 错误码规范

| 错误码区间 | 含义 |
|----------|------|
| 0 | 成功 |
| 1000-1999 | 参数错误 |
| 2000-2999 | 认证错误 |
| 3000-3999 | 权限错误 |
| 4000-4999 | 业务错误（含合规拦截） |
| 5000-5999 | 系统错误 |
| 6000-6999 | 第三方服务错误 |

## 7.4 关键 API 列表

### 数字专员服务（specialist-service）

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/specialists | GET | 专员列表 |
| /api/v1/specialists/{id} | GET | 专员详情 |
| /api/v1/specialists/{id}/chat | POST | 与专员对话 |
| /api/v1/conversations/{session_id} | GET | 会话历史 |
| /api/v1/specialists/{id}/stats | GET | 专员使用统计 |

### 陪访助手服务（visit-service）

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/visits/pre-visit | POST | 拜访前准备包 |
| /api/v1/visits/start | POST | 开始拜访 |
| /api/v1/visits/{id}/transcript | POST | 上传转写 |
| /api/v1/visits/{id}/end | POST | 结束拜访，生成记录 |
| /api/v1/visits/{id}/follow-up | GET | 获取跟进建议 |
| /api/v1/visits | GET | 拜访列表 |

### 知识库服务（knowledge-service）

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/knowledge/search | POST | 检索知识 |
| /api/v1/knowledge/documents | GET | 文档列表 |
| /api/v1/knowledge/documents/{id} | GET | 文档详情 |
| /api/v1/knowledge/upload | POST | 上传文档 |
| /api/v1/knowledge/feedback | POST | 反馈检索质量 |

### 合规审核服务（compliance-service）

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/compliance/check | POST | 检查内容合规 |
| /api/v1/compliance/rules | GET | 规则列表 |
| /api/v1/compliance/rules | POST | 新增规则 |
| /api/v1/compliance/rules/{id} | PUT | 更新规则 |
| /api/v1/compliance/blocks | GET | 拦截记录 |

### 审计服务（audit-service）

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/audit/logs | GET | 审计日志查询 |
| /api/v1/audit/export | POST | 导出审计报告 |
| /api/v1/audit/stats | GET | 审计统计 |

### 医生/专家服务（hcp-service）

| 接口 | 方法 | 说明 |
|------|------|------|
| /api/v1/hcps | GET | 医生列表 |
| /api/v1/hcps/{id} | GET | 医生详情 |
| /api/v1/hcps/{id}/profile | GET | 医生画像 |
| /api/v1/hcps/{id}/interactions | GET | 互动历史 |

---

# 8. 核心模块开发

## 8.1 specialist-service（数字学术专员）

### 8.1.1 目录结构

```
services/specialist-service/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py
│   ├── api/
│   │   ├── specialists.py
│   │   └── conversations.py
│   ├── core/
│   │   ├── specialist.py
│   │   ├── conversation.py
│   │   └── answer_generator.py
│   ├── services/
│   │   ├── bailian_client.py
│   │   ├── qwen_client.py
│   │   ├── knowledge_client.py
│   │   ├── compliance_client.py
│   │   └── audit_client.py
│   ├── models/
│   ├── db/
│   └── utils/
├── tests/
├── requirements.txt
└── Dockerfile
```

### 8.1.2 百炼客户端

```python
# services/bailian_client.py
import os
import requests
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class BailianClient:
    """阿里云百炼平台客户端"""
    
    def __init__(self):
        self.api_key = os.getenv("BAILIAN_API_KEY")
        self.base_url = "https://bailian.aliyuncs.com/v2"
        self.timeout = 30
    
    def chat(
        self,
        app_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        biz_params: Optional[Dict] = None,
    ) -> Dict:
        """调用百炼 App 对话接口"""
        url = f"{self.base_url}/app/{app_id}/completion"
        
        payload = {
            "input": {"prompt": prompt},
            "parameters": {},
            "debug": {}
        }
        if session_id:
            payload["input"]["session_id"] = session_id
        if biz_params:
            payload["input"]["biz_params"] = biz_params
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 200:
                raise BailianException(f"百炼调用失败: {result}")
            
            return result.get("output", {})
        except requests.exceptions.Timeout:
            raise BailianException("百炼调用超时")
        except requests.exceptions.RequestException as e:
            raise BailianException(f"百炼调用异常: {e}")


class BailianException(Exception):
    pass
```

### 8.1.3 通义千问客户端

```python
# services/qwen_client.py
import os
from openai import OpenAI
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class QwenClient:
    """通义千问客户端（OpenAI 兼容接口）"""
    
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "qwen-max",
        temperature: float = 0.1,
        max_tokens: int = 2000,
        **kwargs
    ) -> Dict:
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            return {
                "content": response.choices[0].message.content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
        except Exception as e:
            logger.error(f"通义千问调用失败: {e}")
            raise
    
    def chat_stream(self, messages, model="qwen-max", **kwargs):
        try:
            stream = self.client.chat.completions.create(
                model=model, messages=messages, stream=True, **kwargs
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"通义千问流式调用失败: {e}")
            raise
```

### 8.1.4 答案生成器

```python
# core/answer_generator.py
import time
import re
import uuid
import logging
from typing import Dict, Optional

from app.services.bailian_client import BailianClient, BailianException
from app.services.qwen_client import QwenClient
from app.services.knowledge_client import KnowledgeClient
from app.services.compliance_client import ComplianceClient
from app.services.audit_client import AuditClient
from app.models.specialist import Specialist

logger = logging.getLogger(__name__)


class AnswerGenerator:
    """答案生成器：知识检索 + 大模型 + 合规审核 + 审计"""
    
    def __init__(self):
        self.bailian = BailianClient()
        self.qwen = QwenClient()
        self.knowledge = KnowledgeClient()
        self.compliance = ComplianceClient()
        self.audit = AuditClient()
    
    def generate(
        self,
        question: str,
        specialist: Specialist,
        user_id: int,
        session_id: Optional[str] = None,
    ) -> Dict:
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        try:
            # 1. 知识检索
            logger.info(f"[{request_id}] 开始检索知识")
            knowledge = self.knowledge.search(
                query=question,
                product_id=specialist.product_id,
                top_k=10
            )
            
            # 2. 合规预检（问题本身不能违规）
            question_check = self.compliance.check(
                content=question,
                context={"user_id": user_id, "type": "user_input"}
            )
            if question_check.get("blocked"):
                return {
                    "answer": "您的问题包含不合规内容，请调整后重试",
                    "blocked": True,
                    "violations": question_check.get("violations"),
                    "request_id": request_id
                }
            
            # 3. 调用百炼生成答案
            logger.info(f"[{request_id}] 调用百炼生成答案")
            try:
                bailian_result = self.bailian.chat(
                    app_id=specialist.bailian_app_id,
                    prompt=question,
                    session_id=session_id,
                    biz_params={
                        "knowledge_docs": knowledge,
                        "specialist_name": specialist.name
                    }
                )
                answer = bailian_result.get("text", "")
                citations = bailian_result.get("docs", [])
            except BailianException as e:
                logger.warning(f"百炼调用失败，降级到通义千问: {e}")
                answer = self._fallback_generate(question, specialist, knowledge)
                citations = knowledge[:5]
            
            # 4. 合规审核（答案）
            answer_check = self.compliance.check(
                content=answer,
                context={"user_id": user_id, "type": "ai_output", "specialist_id": specialist.id}
            )
            if answer_check.get("blocked"):
                return {
                    "answer": "该问题建议直接咨询医学顾问",
                    "blocked": True,
                    "violations": answer_check.get("violations"),
                    "request_id": request_id
                }
            
            # 5. 审计日志
            latency_ms = int((time.time() - start_time) * 1000)
            self._log_audit(
                user_id=user_id,
                specialist_id=specialist.id,
                question=question,
                answer=answer,
                citations=citations,
                compliance_result=answer_check,
                request_id=request_id,
                latency_ms=latency_ms,
            )
            
            return {
                "answer": answer,
                "citations": citations,
                "evidence_level": self._extract_evidence_level(answer),
                "session_id": session_id,
                "request_id": request_id,
                "latency_ms": latency_ms,
                "blocked": False
            }
            
        except Exception as e:
            logger.exception(f"[{request_id}] 答案生成失败: {e}")
            raise
    
    def _fallback_generate(
        self, question: str, specialist: Specialist, knowledge: list
    ) -> str:
        """百炼不可用时的降级方案"""
        context = "\n\n".join([
            f"[{i+1}] {doc.get('title', '')}\n{doc.get('content', '')[:500]}"
            for i, doc in enumerate(knowledge[:5])
        ])
        
        prompt = f"""你是{specialist.name}，根据以下参考资料回答代表的问题。

参考资料：
{context}

代表问题：{question}

要求：
1. 简洁回答，不超过 300 字
2. 必须引用参考资料（用 [1][2] 标注）
3. 不确定时建议咨询医学顾问
4. 严禁承诺疗效、提及回扣、讨论医生处方量

回答："""
        
        result = self.qwen.chat(
            messages=[{"role": "user", "content": prompt}],
            model="qwen-max",
            temperature=0.1
        )
        return result["content"]
    
    def _extract_evidence_level(self, answer: str) -> Optional[str]:
        match = re.search(r"【证据等级】\s*([A-D]|专家共识|未知)", answer)
        return match.group(1) if match else None
    
    def _log_audit(self, **kwargs):
        try:
            self.audit.log(**kwargs)
        except Exception as e:
            logger.error(f"审计日志记录失败: {e}")
```

### 8.1.5 API 路由

```python
# api/specialists.py
from fastapi import APIRouter, Depends, HTTPException
import logging

from app.core.answer_generator import AnswerGenerator
from app.db.repositories.specialist_repo import SpecialistRepository
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/v1/specialists", tags=["specialists"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_specialists(
    current_user: dict = Depends(get_current_user),
    repo: SpecialistRepository = Depends()
):
    specialists = repo.list_all(status="active")
    return {
        "code": 0,
        "data": [
            {
                "id": s.id,
                "name": s.name,
                "product_id": s.product_id,
                "status": s.status
            }
            for s in specialists
        ]
    }


@router.get("/{specialist_id}")
async def get_specialist(
    specialist_id: int,
    current_user: dict = Depends(get_current_user),
    repo: SpecialistRepository = Depends()
):
    specialist = repo.get_by_id(specialist_id)
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    return {"code": 0, "data": specialist.to_dict()}


@router.post("/{specialist_id}/chat")
async def chat_with_specialist(
    specialist_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    repo: SpecialistRepository = Depends()
):
    specialist = repo.get_by_id(specialist_id)
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    
    question = request.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    
    session_id = request.get("session_id")
    
    generator = AnswerGenerator()
    result = generator.generate(
        question=question,
        specialist=specialist,
        user_id=current_user["id"],
        session_id=session_id
    )
    
    return {"code": 0, "data": result}
```

### 8.1.6 FastAPI 入口

```python
# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

from app.api import specialists, conversations

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MedAgent - 数字学术专员服务",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(specialists.router)
app.include_router(conversations.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "specialist-service"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SPECIALIST_SERVICE_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

## 8.2 visit-service（陪访助手）

```python
# core/visit_manager.py
import json
import time
import re
import logging
from typing import Dict

from app.services.tingwu_client import TingwuClient
from app.services.compliance_client import ComplianceClient
from app.services.specialist_client import SpecialistClient
from app.services.audit_client import AuditClient

logger = logging.getLogger(__name__)


class VisitManager:
    """拜访流程管理器"""
    
    def __init__(self):
        self.tingwu = TingwuClient()
        self.compliance = ComplianceClient()
        self.specialist = SpecialistClient()
        self.audit = AuditClient()
    
    def prepare_visit(
        self, hcp_id: int, user_id: int, product_id: int
    ) -> Dict:
        """拜访前：生成准备包"""
        hcp_profile = self._get_hcp_profile(hcp_id)
        history = self._get_interaction_history(hcp_id, user_id)
        
        prompt = f"""为医药代表准备拜访以下医生的资料：

医生信息：
- 姓名：{hcp_profile.get('name')}
- 医院科室：{hcp_profile.get('hospital')} {hcp_profile.get('department')}
- 职称：{hcp_profile.get('title')}

历史互动（最近 3 次）：
{json.dumps(history, ensure_ascii=False, indent=2)}

请生成：
1. 3-5 个推荐话题
2. 1-2 个红线提醒
3. 1 段开场白建议
4. 上次未完成的跟进项

输出 JSON 格式。"""
        
        result = self.specialist.generate(prompt=prompt, product_id=product_id)
        
        return {
            "hcp_profile": hcp_profile,
            "history": history,
            "recommendations": result,
            "generated_at": int(time.time())
        }
    
    def start_visit(self, hcp_id: int, user_id: int, product_id: int) -> Dict:
        """开始拜访：创建拜访记录"""
        return {
            "id": self._create_visit_record(hcp_id, user_id, product_id),
            "start_time": int(time.time()),
            "status": "in_progress"
        }
    
    def process_transcript(self, visit_id: int, audio_url: str) -> Dict:
        """处理拜访中对话：ASR + 合规 + 异议"""
        transcript = self.tingwu.transcribe(audio_url)
        recent_text = transcript.get("recent_text", "")
        
        compliance_result = self.compliance.check(
            content=recent_text,
            context={"visit_id": visit_id, "type": "live_conversation"}
        )
        objections = self._detect_objections(recent_text)
        suggestions = self._generate_suggestions(recent_text, objections, compliance_result)
        
        return {
            "transcript": transcript,
            "compliance": compliance_result,
            "objections": objections,
            "suggestions": suggestions
        }
    
    def end_visit(self, visit_id: int, full_transcript: str) -> Dict:
        """结束拜访：生成结构化记录"""
        prompt = f"""根据以下拜访对话，生成结构化拜访记录。

对话全文：
{full_transcript}

输出 JSON：
{{
  "summary": "100字摘要",
  "key_points": ["关键点1", "关键点2"],
  "hcp_interests": ["兴趣点"],
  "hcp_objections": ["异议"],
  "follow_up_suggestions": ["跟进建议"],
  "sentiment": "positive/neutral/negative",
  "next_visit_plan": {{
    "recommended_time": "YYYY-MM-DD",
    "recommended_topics": ["话题"],
    "materials_to_send": ["资料"]
  }}
}}"""
        
        result = self.specialist.generate(prompt=prompt)
        visit_record = self._save_visit_record(visit_id, result)
        self._update_hcp_profile_from_visit(visit_id, result)
        self.audit.log(
            service_name="visit-service",
            action="end_visit",
            resource_type="visit",
            resource_id=str(visit_id),
            after_value=result
        )
        return visit_record
    
    def _detect_objections(self, text: str) -> list:
        patterns = [r"不太.*?效果", r"担心.*?副作用", r"价格.*?贵", r"已经有.*?用"]
        objections = []
        for p in patterns:
            objections.extend(re.findall(p, text))
        return objections
    
    def _generate_suggestions(self, transcript, objections, compliance_result) -> Dict:
        return {
            "objection_responses": [
                {"objection": o, "response": "建议引用 III 期数据..."}
                for o in objections
            ],
            "compliance_warnings": compliance_result.get("violations", [])
        }
```

---

# 9. AI 能力实现

## 9.1 文档处理流水线

```python
# services/document_processor.py
import os
import requests
import pypdf
from docx import Document
import dashscope
from http import HTTPStatus
import logging

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """文档处理：解析 -> 切分 -> 向量化 -> 入库"""
    
    def __init__(self):
        from app.services.dashvector_client import DashVectorClient
        self.dashvector = DashVectorClient()
    
    def process_document(self, file_url: str, doc_meta: Dict) -> int:
        # 1. 下载
        file_path = self._download(file_url)
        
        # 2. 解析
        if file_path.endswith(".pdf"):
            content = self._parse_pdf(file_path)
        elif file_path.endswith(".docx"):
            content = self._parse_docx(file_path)
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        
        # 3. 切分
        chunks = self._split(content)
        
        # 4. 入库 + 向量化
        doc_id = self._save_doc(doc_meta, content[:5000], file_url)
        for i, chunk in enumerate(chunks):
            vector = self._embed(chunk["content"])
            self.dashvector.upsert(
                collection="knowledge_base",
                doc_id=f"doc_{doc_id}_chunk_{i}",
                vector=vector,
                fields={
                    "doc_id": doc_id,
                    "title": doc_meta.get("title"),
                    "doc_type": doc_meta.get("doc_type"),
                    "product_id": doc_meta.get("product_id"),
                    "evidence_level": doc_meta.get("evidence_level"),
                    "chunk_index": i,
                    "content": chunk["content"]
                }
            )
        return doc_id
    
    def _parse_pdf(self, path):
        reader = pypdf.PdfReader(path)
        return "\n".join(p.extract_text() for p in reader.pages)
    
    def _parse_docx(self, path):
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    
    def _split(self, content, chunk_size=512):
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        chunks, current, current_size = [], "", 0
        for para in paragraphs:
            size = len(para) // 2
            if current_size + size > chunk_size:
                if current:
                    chunks.append({"content": current.strip()})
                current, current_size = para, size
            else:
                current += "\n\n" + para
                current_size += size
        if current:
            chunks.append({"content": current.strip()})
        return chunks
    
    def _embed(self, text):
        dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
        resp = dashscope.TextEmbedding.call(
            model="text-embedding-v3",
            input=text[:2048]
        )
        if resp.status_code == HTTPStatus.OK:
            return resp.output["embeddings"][0]["embedding"]
        raise Exception("向量化失败")
    
    def _download(self, url):
        local = f"/tmp/{os.path.basename(url)}"
        r = requests.get(url, stream=True)
        with open(local, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return local
```

## 9.2 知识检索

```python
# services/knowledge_client.py
import os
import requests
import dashscope
from http import HTTPStatus
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class KnowledgeClient:
    """知识库检索"""
    
    def __init__(self):
        self.api_key = os.getenv("DASHVECTOR_API_KEY")
        self.endpoint = os.getenv("DASHVECTOR_ENDPOINT")
        self.collection = "knowledge_base"
    
    def search(
        self, query: str, product_id: Optional[int] = None,
        doc_type: Optional[str] = None, top_k: int = 10
    ) -> List[Dict]:
        # 1. 向量化
        query_vector = self._embed(query)
        
        # 2. DashVector 检索
        results = self._vector_search(query_vector, product_id, doc_type, top_k * 2)
        
        # 3. 重排
        return self._rerank(query, results, top_k)
    
    def _embed(self, text):
        dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
        resp = dashscope.TextEmbedding.call(
            model="text-embedding-v3",
            input=text[:2048]
        )
        if resp.status_code == HTTPStatus.OK:
            return resp.output["embeddings"][0]["embedding"]
        raise Exception("向量化失败")
    
    def _vector_search(self, vector, product_id, doc_type, top_k):
        url = f"{self.endpoint}/v1/collections/{self.collection}/query"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        filter_expr = None
        if product_id:
            filter_expr = f"product_id = {product_id}"
        if doc_type:
            f2 = f"doc_type = '{doc_type}'"
            filter_expr = f"{filter_expr} AND {f2}" if filter_expr else f2
        
        payload = {
            "vector": vector, "topk": top_k,
            "include_vector": False, "filter": filter_expr
        }
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return [
            {"id": m["id"], "score": m["score"], **m.get("fields", {})}
            for m in r.json().get("output", [])
        ]
    
    def _rerank(self, query, results, top_k):
        keywords = set(query.lower().split())
        for r in results:
            content = (r.get("content", "") or "").lower()
            kw_score = sum(1 for k in keywords if k in content) / max(len(keywords), 1)
            r["final_score"] = r["score"] * 0.7 + kw_score * 0.3
        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results[:top_k]
```

## 9.3 话术模板

`shared/prompts/oncology_specialist.yaml`：

```yaml
产品: 肿瘤专员
版本: 1.0.0
模型: qwen-max
温度: 0.1
最大tokens: 2000

system_prompt: |
  # 角色
  你是肿瘤产品 AI 学术专员，名叫「小 K」。
  
  # 职责
  帮助医药代表快速准确地回答肿瘤产品相关问题。
  
  # 必须遵守
  1. 任何回答必须有文献或说明书引用
  2. 证据等级必须标注（A/B/C/专家共识/未知）
  3. 个体化用药必须建议"咨询医学顾问"
  4. 不确定时明说"该问题建议咨询医学顾问"
  
  # 严禁出现
  - 承诺疗效
  - 提及回扣
  - 讨论医生处方量
  - 超适应症推广
  - 贬低竞品

知识范围:
  允许引用:
    - XX 注射液说明书
    - XX 注射液相关 III 期临床研究
    - NCCN 指南（中国版）
    - CSCO 指南
  禁止引用:
    - 未审核的内部资料
    - 竞品详细数据

合规级别: internal
```

## 9.4 AI 评估

```python
# tests/eval_specialist.py
import json
import sys
import os
import re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.bailian_client import BailianClient
from app.services.compliance_client import ComplianceClient


class SpecialistEvaluator:
    def __init__(self):
        self.bailian = BailianClient()
        self.compliance = ComplianceClient()
    
    def run(self, eval_set_path: str):
        with open(eval_set_path, "r", encoding="utf-8") as f:
            eval_set = json.load(f)
        
        results = []
        for case in eval_set:
            results.append(self._evaluate_case(case))
        
        total = len(results)
        passed = sum(1 for r in results if r["passed"])
        print(f"评估完成：{passed}/{total} 通过 ({passed/total*100:.1f}%)")
        
        with open("eval_report.json", "w", encoding="utf-8") as f:
            json.dump({"total": total, "passed": passed, "details": results},
                      f, ensure_ascii=False, indent=2)
    
    def _evaluate_case(self, case):
        question = case["question"]
        should_be_blocked = case.get("should_be_blocked", False)
        expected_evidence = case.get("expected_evidence_level")
        
        try:
            response = self.bailian.chat(
                app_id=case.get("bailian_app_id", "default"),
                prompt=question
            )
            answer = response.get("text", "")
            blocked = False
        except:
            answer, blocked = "", True
        
        if not blocked:
            check = self.compliance.check(answer, {"type": "eval"})
            blocked = check.get("blocked", False)
        
        has_citation = bool(re.search(r"\[.*?\]|【.*?】", answer))
        evidence_ok = (not expected_evidence) or (expected_evidence in answer)
        
        return {
            "case_id": case.get("id"),
            "question": question,
            "answer": answer,
            "scores": {
                "has_citation": has_citation,
                "evidence_correct": evidence_ok,
                "compliance_correct": blocked == should_be_blocked
            },
            "passed": has_citation and evidence_ok and blocked == should_be_blocked
        }


if __name__ == "__main__":
    SpecialistEvaluator().run("tests/eval_sets/oncology_v1.json")
```

---

# 10. 合规审核实现

## 10.1 合规规则

`shared/compliance-rules/rules.yaml`：

```yaml
rules:
  - id: "R001"
    name: "禁止承诺疗效"
    type: "keyword"
    patterns:
      - "保证治好"
      - "100%有效"
      - "100% 有效"
      - "吃了就好"
      - "一定能治好"
    severity: "high"
    action: "reject"
    enabled: true

  - id: "R002"
    name: "禁止回扣暗示"
    type: "regex"
    patterns:
      - "返[点红]"
      - "提成费"
      - "好处费"
      - "私下给"
    severity: "high"
    action: "reject"
    enabled: true

  - id: "R003"
    name: "禁止统方"
    type: "semantic"
    description: "询问或讨论医生处方量"
    severity: "high"
    action: "reject"
    enabled: true

  - id: "R004"
    name: "禁止超适应症推广"
    type: "semantic"
    description: "推广说明书外的适应症"
    severity: "high"
    action: "reject"
    enabled: true
```

## 10.2 合规审核服务

```python
# services/compliance-service/app/core/checker.py
import yaml
import re
import os
import json
from typing import Dict, List
import logging

from app.services.qwen_client import QwenClient

logger = logging.getLogger(__name__)


class ComplianceChecker:
    """合规审核器：关键词 + 规则 + LLM 兜底"""
    
    def __init__(self):
        self.qwen = QwenClient()
        self.rules = self._load_rules()
        self._compile()
    
    def _load_rules(self):
        path = "shared/compliance-rules/rules.yaml"
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return [r for r in config.get("rules", []) if r.get("enabled", True)]
    
    def _compile(self):
        for rule in self.rules:
            if rule["type"] == "keyword":
                rule["_compiled"] = list(rule["patterns"])
            elif rule["type"] == "regex":
                rule["_compiled"] = [re.compile(p) for p in rule["patterns"]]
    
    def check(self, content: str, context: Dict) -> Dict:
        violations, checked = [], []
        
        # 第 1 关：关键词
        for rule in self.rules:
            if rule["type"] in ("keyword", "regex"):
                checked.append(rule["id"])
                matched = self._match_keyword(content, rule)
                if matched:
                    violations.append({
                        "rule_code": rule["id"],
                        "rule_name": rule["name"],
                        "severity": rule["severity"],
                        "action": rule["action"],
                        "matched_text": matched
                    })
        
        if any(v["action"] == "reject" for v in violations):
            return {"blocked": True, "violations": violations,
                    "risk_level": "high", "checked_rules": checked}
        
        # 第 2 关：LLM 语义
        semantic_violations = self._llm_check(content, context)
        violations.extend(semantic_violations)
        
        blocked = any(v["action"] == "reject" for v in violations)
        risk = "high" if any(v["severity"] == "high" for v in violations) else \
               "medium" if any(v["severity"] == "medium" for v in violations) else "low"
        
        return {"blocked": blocked, "violations": violations,
                "risk_level": risk, "checked_rules": checked}
    
    def _match_keyword(self, content, rule):
        for p in rule["_compiled"]:
            if rule["type"] == "keyword" and p in content:
                return p
            elif rule["type"] == "regex":
                m = p.search(content)
                if m:
                    return m.group()
        return None
    
    def _llm_check(self, content, context) -> List[Dict]:
        semantic_rules = [r for r in self.rules if r["type"] == "semantic"]
        if not semantic_rules:
            return []
        
        rules_desc = "\n".join([
            f"- {r['id']}: {r['name']}（{r.get('description', '')}）"
            for r in semantic_rules
        ])
        
        prompt = f"""你是药企合规审核员。检查以下内容是否违反合规规则。

合规规则：
{rules_desc}

待检查内容：
{content}

输出 JSON：
{{"violations": [{{"rule_code": "R003", "matched_text": "...", "reason": "..."}}]}}

如果内容合规，violations 为空数组。"""
        
        try:
            result = self.qwen.chat(
                messages=[{"role": "user", "content": prompt}],
                model="qwen-turbo",
                temperature=0.0
            )
            parsed = json.loads(result["content"])
            violations = []
            for v in parsed.get("violations", []):
                rule = next((r for r in semantic_rules if r["id"] == v["rule_code"]), None)
                if rule:
                    violations.append({
                        "rule_code": v["rule_code"],
                        "rule_name": rule["name"],
                        "severity": rule["severity"],
                        "action": rule["action"],
                        "matched_text": v.get("matched_text", "")
                    })
            return violations
        except Exception as e:
            logger.error(f"LLM 合规审核失败: {e}")
            return []
```

## 10.3 审计日志

```python
# services/audit-service/app/core/logger.py
import os
import hashlib
from datetime import datetime
import logging

from app.db.session import get_db
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class AuditLogger:
    """审计日志记录器"""
    
    def log(
        self, service_name, user_id, action,
        resource_type=None, resource_id=None,
        before_value=None, after_value=None,
        ai_involved=False, ai_model=None,
        ai_prompt=None, ai_response=None,
        compliance_result=None, request_id=None,
        client_ip=None, user_agent=None,
    ):
        try:
            ai_prompt_hash = hashlib.sha256(ai_prompt.encode()).hexdigest() if ai_prompt else None
            ai_response_hash = hashlib.sha256(ai_response.encode()).hexdigest() if ai_response else None
            risk_level = compliance_result.get("risk_level") if compliance_result else None
            
            db = next(get_db())
            log = AuditLog(
                timestamp=datetime.utcnow(),
                service_name=service_name,
                user_id=user_id, action=action,
                resource_type=resource_type, resource_id=resource_id,
                before_value=before_value, after_value=after_value,
                ai_involved=ai_involved, ai_model=ai_model,
                ai_prompt_hash=ai_prompt_hash, ai_response_hash=ai_response_hash,
                compliance_result=compliance_result, risk_level=risk_level,
                client_ip=client_ip, user_agent=user_agent,
                request_id=request_id
            )
            db.add(log)
            db.commit()
        except Exception as e:
            logger.error(f"审计日志记录失败: {e}")
```

---

# 11. 移动端开发

## 11.1 React Native 项目结构

```
mobile/
├── src/
│   ├── App.tsx
│   ├── navigation/
│   │   ├── AppNavigator.tsx
│   │   └── types.ts
│   ├── screens/
│   │   ├── Login/
│   │   ├── Home/
│   │   ├── Specialists/
│   │   ├── Chat/
│   │   ├── VisitPrepare/
│   │   ├── VisitInProgress/
│   │   ├── VisitEnd/
│   │   ├── HCPSearch/
│   │   ├── HCPDetail/
│   │   ├── Content/
│   │   ├── Compliance/
│   │   └── Profile/
│   ├── components/
│   ├── api/
│   │   ├── client.ts
│   │   ├── specialist.ts
│   │   ├── visit.ts
│   │   └── compliance.ts
│   ├── store/
│   ├── utils/
│   ├── hooks/
│   ├── constants/
│   └── types/
├── ios/
├── android/
└── package.json
```

## 11.2 关键页面

### 11.2.1 数字专员对话页

```typescript
// src/screens/Chat/ChatScreen.tsx
import React, { useState, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator
} from 'react-native';
import { sendMessage } from '../../api/specialist';

export default function ChatScreen({ route }: any) {
  const { specialistId, specialistName } = route.params;
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const flatListRef = useRef<FlatList>(null);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userMsg = { id: Date.now().toString(), role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    const question = input;
    setInput('');
    setLoading(true);
    
    try {
      const response = await sendMessage(specialistId, {
        question,
        session_id: `sess_${specialistId}_${Date.now()}`
      });
      const aiMsg = {
        id: response.request_id,
        role: 'assistant',
        content: response.answer,
        citations: response.citations,
        evidenceLevel: response.evidence_level
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch (error: any) {
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: error.message || '出错了，请重试'
      }]);
    } finally {
      setLoading(false);
    }
  };

  const renderMessage = ({ item }: { item: any }) => {
    const isUser = item.role === 'user';
    return (
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.aiBubble]}>
        <Text style={isUser ? styles.userText : styles.aiText}>
          {item.content}
        </Text>
        {!isUser && item.citations && item.citations.length > 0 && (
          <View style={styles.citations}>
            <Text style={styles.citationTitle}>引用来源：</Text>
            {item.citations.map((c: any, i: number) => (
              <Text key={i} style={styles.citation}>[{i + 1}] {c.title}</Text>
            ))}
          </View>
        )}
        {!isUser && item.evidenceLevel && (
          <Text style={styles.evidence}>证据等级：{item.evidenceLevel}</Text>
        )}
      </View>
    );
  };

  return (
    <KeyboardAvoidingView style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>{specialistName}</Text>
      </View>
      <FlatList
        ref={flatListRef}
        data={messages}
        renderItem={renderMessage}
        keyExtractor={item => item.id}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => flatListRef.current?.scrollToEnd()}
      />
      <View style={styles.inputBar}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="问数字专员..."
          multiline
        />
        <TouchableOpacity
          style={styles.sendBtn}
          onPress={handleSend}
          disabled={loading}
        >
          {loading ? <ActivityIndicator color="#fff" /> :
            <Text style={styles.sendText}>发送</Text>}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  header: { backgroundColor: '#3b82f6', padding: 16, paddingTop: 50 },
  headerTitle: { color: '#fff', fontSize: 18, fontWeight: '600' },
  list: { padding: 16 },
  bubble: { padding: 12, borderRadius: 8, marginBottom: 8, maxWidth: '80%' },
  userBubble: { alignSelf: 'flex-end', backgroundColor: '#3b82f6' },
  aiBubble: { alignSelf: 'flex-start', backgroundColor: '#fff' },
  userText: { color: '#fff', fontSize: 15 },
  aiText: { color: '#000', fontSize: 15 },
  citations: { marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: '#eee' },
  citationTitle: { fontSize: 12, color: '#666', marginBottom: 4 },
  citation: { fontSize: 12, color: '#666' },
  evidence: { marginTop: 4, fontSize: 12, color: '#999' },
  inputBar: { flexDirection: 'row', padding: 8, backgroundColor: '#fff',
    borderTopWidth: 1, borderTopColor: '#eee' },
  input: { flex: 1, padding: 8, fontSize: 15, maxHeight: 100 },
  sendBtn: { backgroundColor: '#3b82f6', paddingHorizontal: 16, paddingVertical: 8,
    borderRadius: 8, marginLeft: 8, justifyContent: 'center' },
  sendText: { color: '#fff', fontWeight: '600' }
});
```

### 11.2.2 拜访前准备页

```typescript
// src/screens/VisitPrepare/VisitPrepareScreen.tsx
import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { prepareVisit } from '../../api/visit';

export default function VisitPrepareScreen({ route }: any) {
  const { hcpId, productId } = route.params;
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    prepareVisit({ hcpId, productId }).then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) return <ActivityIndicator style={{flex:1}} size="large" />;
  if (!data) return <Text>加载失败</Text>;

  const { hcp_profile, recommendations } = data;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>医生信息</Text>
        <Text style={styles.label}>姓名：{hcp_profile.name}</Text>
        <Text style={styles.label}>医院：{hcp_profile.hospital}</Text>
        <Text style={styles.label}>科室：{hcp_profile.department}</Text>
        <Text style={styles.label}>职称：{hcp_profile.title}</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>推荐话题</Text>
        {recommendations.topics?.map((t: string, i: number) => (
          <Text key={i} style={styles.item}>- {t}</Text>
        ))}
      </View>

      <View style={[styles.card, styles.warningCard]}>
        <Text style={[styles.cardTitle, {color: '#fff'}]}>红线提醒</Text>
        {recommendations.red_lines?.map((r: string, i: number) => (
          <Text key={i} style={[styles.item, {color: '#fff'}]}>- {r}</Text>
        ))}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>开场白建议</Text>
        <Text style={styles.quote}>{recommendations.opening}</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  card: { backgroundColor: '#fff', margin: 12, padding: 16, borderRadius: 8 },
  warningCard: { backgroundColor: '#dc2626' },
  cardTitle: { fontSize: 16, fontWeight: '600', marginBottom: 12 },
  label: { fontSize: 14, color: '#666', marginBottom: 4 },
  item: { fontSize: 14, color: '#333', marginBottom: 4 },
  quote: { fontSize: 14, color: '#666', fontStyle: 'italic' }
});
```

## 11.3 API 客户端

```typescript
// src/api/client.ts
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

const API_BASE_URL = Platform.OS === 'web'
  ? 'http://localhost:8000'
  : 'https://api.medagent.example.com';

class APIClient {
  private baseURL = API_BASE_URL;
  private token: string | null = null;

  async setToken(token: string) {
    this.token = token;
    await AsyncStorage.setItem('token', token);
  }

  async request<T>(method: string, path: string, data?: any): Promise<T> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.token) headers['Authorization'] = `Bearer ${this.token}`;
    headers['X-Request-ID'] = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
    
    const response = await fetch(`${this.baseURL}${path}`, {
      method,
      headers,
      body: data ? JSON.stringify(data) : undefined
    });
    const result = await response.json();
    if (result.code !== 0) throw new APIError(result.message, result.code);
    return result.data;
  }
}

export class APIError extends Error {
  constructor(message: string, public code: number) { super(message); }
}

export const apiClient = new APIClient();
```

```typescript
// src/api/specialist.ts
import { apiClient } from './client';

export async function sendMessage(specialistId: number, params: { question: string; session_id?: string }) {
  return apiClient.request('POST', `/api/v1/specialists/${specialistId}/chat`, params);
}

export async function listSpecialists() {
  return apiClient.request('GET', '/api/v1/specialists');
}
```

---

# 12. 知识库构建

## 12.1 知识库内容清单

| 类型 | 数量 | 来源 |
|------|------|------|
| 产品说明书 | 1-3 个 | 内部资料 |
| 关键临床文献 | 100-300 篇 | PubMed、CNKI |
| 临床指南/共识 | 5-15 个 | 权威机构 |
| 法规政策 | 10-30 个 | NMPA 官网 |
| 竞品说明书 | 3-5 个 | 公开资料 |

## 12.2 知识库构建脚本

```python
# scripts/build_knowledge_base.py
import os
import sys
import argparse
import glob
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.document_processor import DocumentProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", required=True)
    parser.add_argument("--dir")
    args = parser.parse_args()
    
    docs_dir = args.dir or f"knowledge-base/{args.product}"
    if not os.path.exists(docs_dir):
        logger.error(f"目录不存在: {docs_dir}")
        return
    
    processor = DocumentProcessor()
    files = [f for f in glob.glob(f"{docs_dir}/**/*", recursive=True)
             if os.path.isfile(f) and f.endswith(('.pdf', '.docx', '.txt'))]
    
    success, failed = 0, 0
    for file_path in files:
        try:
            from app.services.oss_client import OSSClient
            oss = OSSClient()
            file_url = oss.upload_local_file(file_path)
            
            doc_meta = {
                "title": os.path.basename(file_path).replace(".pdf", ""),
                "doc_type": infer_doc_type(file_path),
                "product_id": get_product_id(args.product),
                "evidence_level": infer_evidence_level(file_path)
            }
            doc_id = processor.process_document(file_url, doc_meta)
            logger.info(f"OK {file_path} -> doc_id={doc_id}")
            success += 1
        except Exception as e:
            logger.error(f"FAIL {file_path} 失败: {e}")
            failed += 1
    
    logger.info(f"构建完成：成功 {success}, 失败 {failed}")


def infer_doc_type(path):
    name = os.path.basename(path).lower()
    if "说明书" in name: return "product"
    if "指南" in name or "共识" in name: return "guideline"
    if "政策" in name or "法规" in name: return "regulation"
    if "竞品" in name: return "competitor"
    return "literature"


def infer_evidence_level(path):
    name = os.path.basename(path).lower()
    if "meta" in name or "系统评价" in name: return "A"
    if "iii期" in name or "rct" in name: return "B"
    if "ii期" in name: return "B"
    if "综述" in name: return "B"
    if "共识" in name or "指南" in name: return "expert_opinion"
    return "unknown"


def get_product_id(code):
    from app.db.session import get_db
    from app.models.product import Product
    db = next(get_db())
    p = db.query(Product).filter(Product.product_code == code).first()
    return p.id if p else None


if __name__ == "__main__":
    main()
```

```bash
# 使用示例
python scripts/build_knowledge_base.py --product oncology
```

---

# 13. 代码规范

## 13.1 Python 规范

```python
# 使用 Black + isort + mypy + flake8
# 命名：类 PascalCase，函数/变量 snake_case，常量 UPPER_SNAKE_CASE
```

`pyproject.toml`：

```toml
[tool.black]
line-length = 100
target-version = ["py311"]

[tool.isort]
profile = "black"
line_length = 100

[tool.mypy]
python_version = "3.11"
strict = true
```

## 13.2 TypeScript 规范

```json
{
  "extends": ["@react-native-community/eslint-config", "prettier"],
  "rules": {
    "no-console": "warn",
    "prefer-const": "error"
  }
}
```

## 13.3 Git 规范

分支命名：
- feature/specialist-chat
- fix/compliance-rule-bug
- refactor/extract-service

Commit 信息：
- feat(specialist): add multi-product coordination
- fix(compliance): handle empty content
- docs(api): update auth specification
- refactor(db): extract repository pattern
- test(eval): add new evaluation cases

## 13.4 API 命名

```
GET    /api/v1/specialists
GET    /api/v1/specialists/{id}
POST   /api/v1/specialists/{id}/chat
POST   /api/v1/specialists
PUT    /api/v1/specialists/{id}
DELETE /api/v1/specialists/{id}
```

---

# 14. 测试规范

## 14.1 单元测试

```python
# tests/test_compliance.py
import pytest
from app.core.checker import ComplianceChecker


class TestComplianceChecker:
    def setup_method(self):
        self.checker = ComplianceChecker()
    
    def test_keyword_block(self):
        result = self.checker.check("我们这个药保证治好", {"scenario": "chat"})
        assert result["blocked"] is True
        assert any(v["rule_code"] == "R001" for v in result["violations"])
    
    def test_safe_content_passes(self):
        result = self.checker.check(
            "我们的药在临床试验中显示出良好的疗效",
            {"scenario": "chat"}
        )
        assert result["blocked"] is False
    
    def test_empty_content(self):
        result = self.checker.check("", {"scenario": "chat"})
        assert "blocked" in result
```

## 14.2 集成测试

```python
# tests/integration/test_specialist_flow.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestSpecialistFlow:
    def test_full_chat_flow(self):
        login = client.post("/api/v1/auth/login", json={
            "username": "test_rep", "password": "test_pass"
        })
        token = login.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        specialists = client.get("/api/v1/specialists", headers=headers)
        specialist_id = specialists.json()["data"][0]["id"]
        
        response = client.post(
            f"/api/v1/specialists/{specialist_id}/chat",
            json={"question": "肺癌患者用我们的药，需要注意什么？"},
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert "answer" in data
        assert len(data["citations"]) > 0
```

## 14.3 AI 评估

```bash
python tests/eval_specialist.py
# 输出：评估完成：42/50 通过 (84.0%)
```

---

# 15. 部署上线

## 15.1 环境分层

| 环境 | 用途 | 部署位置 |
|------|------|---------|
| dev | 开发联调 | 本地 Docker |
| test | 自动化测试 | 阿里云测试 |
| staging | 预发验证 | 阿里云预发 |
| prod | 生产 | 阿里云生产 |

## 15.2 Docker

每个微服务的 `Dockerfile`：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY shared/ ./shared/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
```

## 15.3 CI/CD

`.github/workflows/deploy.yml`：

```yaml
name: Build and Deploy

on:
  push:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install
        run: pip install -r requirements.txt && pip install pytest pytest-cov
      - name: Test
        env:
          DASHSCOPE_API_KEY: ${{ secrets.DASHSCOPE_API_KEY }}
        run: pytest --cov=services --cov-report=xml

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Build
        run: |
          docker build -t medagent/specialist-service:${{ github.sha }} \
            -f services/specialist-service/Dockerfile .
      - name: Push
        run: |
          docker login --username=${{ secrets.ALIYUN_REGISTRY_USER }} \
            --password=${{ secrets.ALIYUN_REGISTRY_PASS }} \
            registry.cn-hangzhou.aliyuncs.com
          docker push registry.cn-hangzhou.aliyuncs.com/medagent/specialist-service:${{ github.sha }}
```

## 15.4 监控告警

```yaml
# 阿里云 ARMS
alerts:
  - name: AI 回答延迟过高
    metric: specialist_chat_latency_p95
    threshold: "> 5000ms"
    notify: [dev_team]
  
  - name: 合规拦截率异常
    metric: compliance_block_rate
    threshold: "< 0.1% or > 10%"
    notify: [dev_team, compliance_team]
  
  - name: 数据库连接池满
    metric: db_connection_pool_usage
    threshold: "> 80%"
    notify: [dev_team]
```

---

# 附录 · 目录结构与命名

```
medagent/                 # 主仓库
medagent-mobile/          # 移动端（如果拆开）
medagent-docs/            # 文档（如果拆开）
```

服务命名：
- specialist-service
- visit-service
- knowledge-service
- compliance-service
- audit-service
- hcp-service

镜像命名：
```
registry.cn-hangzhou.aliyuncs.com/medagent/specialist-service:v1.0.0
```

数据库命名：
- medagent（主库）
- medagent_test（测试）
- medagent_audit（审计独立库）

---

**本手册为开发执行的唯一参考。**
**版本：v4.0 · 2026-07-31**
