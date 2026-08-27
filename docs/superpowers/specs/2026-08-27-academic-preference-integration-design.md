# 学术偏好接入设计（2026-08-27）

## 背景

医生端已有学术偏好画像 `doctor_profiles`（`interest_areas` 兴趣领域 / `preferred_doc_type` 文档类型 / `preferred_style` 风格 / `closed` 关闭个性化开关）。此前偏好**只采集、未消费**：仅 `GET /api/v1/doctor-profiles/briefing` 一个简化版建议端点用了它，医学问答、分身对话、学术卡片推送、夜间简报均未接入。

本文档设计如何把偏好真正接入这些链路，同时守住医疗信息合规底线。

## 目标与决策记录

| 决策点 | 结论 | 理由 |
|---|---|---|
| 接入范围 | **四条链路全接入** | 用户拍板 |
| 个性化深度 | **检索排序层**（回答内容零扰动） | 医学事实不被偏好扭曲是底线 |
| 架构约束下的调整 | 问答=排序层；分身=提示注入；卡片=兴趣匹配标记；**简报保持现状** | 分身检索在百炼内部（纯排序无空间）、简报源自对话汇总（无检索可排序） |
| 卡片推送语义 | **matched_interest 标记**（不改变推送行为、不丢触达） | 推送是一次性批量（无顺序消费点），"排序优先"无实际作用，改为标记 |
| 回退开关 | `closed=true` 或偏好为空 → 全部基线回退 | 尊重医生关闭个性化 |

## 范围

### 做
1. 医学问答：检索结果按偏好 re-rank（排序层）
2. 分身对话：偏好作为 prompt 上下文注入百炼（提示层，带事实约束）
3. 学术卡片推送：`card_push_records` 加 `matched_interest` 标记（B 期推送填充）
4. 共享工具模块 `preference_ranking.py`
5. 迁移 026：`card_push_records.matched_interest BOOLEAN NULL`

### 不做
- 夜间简报个性化（简报内容源自当天对话汇总，无知识库检索可排序；现有简化版建议保留）
- 回答内容按偏好定制（超"检索排序层"红线）
- 卡片推送的偏好过滤（不丢触达）

## 架构

新增 `services/specialist-service/app/core/preference_ranking.py`，三条链路复用：

```
preference_ranking.py
├─ get_profile(db, doctor_id) → DoctorProfile | None   # closed/空 → None
├─ reorder_results(results, profile) → 排序后结果       # 问答
├─ matched_interest(card_title, profile) → bool         # 卡片
└─ preference_context(profile) → str                    # 分身 prompt 片段
```

统一行为：
- `closed=true` 或偏好为空 → 基线（原序 / `false` / 空片段），**零扰动**
- 偏好读取异常 → 静默回退基线，不阻塞业务
- 读取用 `shared/models/doctor_profile.py` 的 ORM 模型（同一 DB）

## 各链路接入

### 1. 医学问答（`app/api/medical.py`）

`_retrieve(question)` 返回后：

```python
profile = preference_ranking.get_profile(db, current_user["id"])
results = preference_ranking.reorder_results(retrieved.get("results") or [], profile)
```

再以排序后的 `results` 走既有 `_build_prompt` → qwen 生成。**qwen 生成逻辑、JSON 契约、引用编号全部不变**——re-rank 只改变片段顺序（引用编号 `cited` 随排序后列表映射，引用溯源正确）。

### 2. 分身对话（`app/core/answer_generator.py`）

`generate_stream` 里、调用百炼/降级 qwen 前：

```python
ctx = preference_ranking.get_profile(db, user_id)
pref = preference_ranking.preference_context(ctx)  # '' 当 closed/空
prompt = f"{question}\n{pref}" if pref else question
```

- 百炼路径（`chat_stream(prompt=...)`）与降级 qwen 路径（`_fallback_generate`）**都注入**，保持一致
- 注入片段带硬约束：「以上医生偏好仅供组织回答侧重，不得改变医学事实、不得省略关键信息」
- 流式门禁、合规检查（`check_compliance`）不动

### 3. 学术卡片推送（`app/api/academic_cards.py` 的 `POST /{card_id}/push`）

push 循环（写 `card_push_records` 处）内对每个目标医生：

```python
profiles = preference_ranking.get_profiles_batch(db, doctor_ids)  # IN 批量查
matched = preference_ranking.matched_interest(card.title, profiles[doctor_id])
```

写入 `card_push_records.matched_interest`（可空；B 期推送填充，历史行为不变）。

## 打分规则（reorder_results）

对每条结果：
- `title + content` 与 `interest_areas` 词匹配 → +1 权重
- 结果含 `doc_type` 且匹配 `preferred_doc_type` → +1（字段缺失则忽略）
- **集合不变只变顺序**；同权重保持原序（稳定排序）
- 权重仅作排序，不进入回答内容

## 合规约束

- 医学事实零扰动（排序不改集合；注入带事实约束文案）
- 合规检查 fail-closed 全部保留（问答 pre/post check、分身流式门禁）
- `closed=true` / 偏好空 / 读取异常 → 基线回退
- 引用溯源、审计留痕不变（不新增个性化审计标记，保持现有审计）

## 迁移

**026_card_push_records_matched_interest.sql**（并入 init_db.sql）：

```sql
ALTER TABLE card_push_records ADD COLUMN matched_interest BOOLEAN NULL;
```

历史推送行为不变，仅 B 期新推送填充。

## 测试

| 层 | 用例 |
|---|---|
| preference_ranking 单元 | 词匹配打分 / 稳定排序 / closed 原序 / 空偏好原序 / 异常回退 |
| 问答 re-rank | 偏好命中片段排前；closed 时与原序一致；cited 映射正确 |
| 分身 prompt 注入 | 偏好片段存在且带事实约束；closed 时无注入；百炼与降级都注入 |
| 卡片 matched_interest | 匹配/不匹配/closed 标记正确；批量读 profile 一次查询 |
| 迁移 026 | 新列可空、历史行不受影响 |

## 明确不做（防误以为已做）

- 夜间简报个性化：保持现状（`doctor-profiles/briefing` 简化版建议保留）
- 回答内容个性化定制（超检索排序层红线）
- 卡片推送偏好过滤（不丢触达，只加标记）
