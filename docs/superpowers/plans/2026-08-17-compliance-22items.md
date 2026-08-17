# 22 项禁止行为清单映射（一期 D）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 2026《医药代表管理办法》（七部门联合发布，2026-08-01 施行）22 项禁止行为清单映射进平台：可内容检测的映射为合规规则（R008-R011 新增 + R006 扩充），行为/流程类映射到平台管控点，产出 22 项全覆盖矩阵文档，完成一期"三层合规拦截（扩充至 22 项清单映射）"的承诺。

**Architecture:** 规则落在现有三层审核体系（keyword → regex → semantic LLM）：`shared/compliance-rules/rules.yaml` 加 R008-R011 种子 + 迁移 010 幂等同步进 `compliance_rules` 表（DB 为源，同 004 机制）+ `init_db.sql` 种子同步；`/redlines` 红线清单与 fast 流式门禁自动纳入新规则（零代码改动）；22 项映射矩阵落 `docs/compliance-2026-22items-matrix.md`（可拦截 → 规则码；流程类 → 平台管控点 + 挂账）。

**Tech Stack:** 纯配置 + 文档 + SQL 迁移 + 测试；无新依赖。

## Global Constraints

- 提交格式：conventional commits，末尾 `Co-Authored-By: Claude <noreply@anthropic.com>`；计划完成后推 origin=Codeup（用户确认）。
- 测试在服务目录下跑：`cd services/compliance-service && python -m pytest tests/ -v`（当前基线 97 passed，本计划后预期 103）。
- 规则体系铁律（必须遵守，违反即返工）：
  - **DB 为源**：迁移只插新增行/更新改动行，**绝不回写 R001-R007 未改动的行**（004 教训：一次性同步后运营修改走管理后台，回写会覆盖后台改动）。
  - enabled 唯一过滤点在 `_reload_rules` 第 3 步；DB 禁用行压掉 YAML 同 id。
  - 坏正则单条剔除不拖垮引擎；keyword/regex 的 pattern 与内容同口径 NFKC+零宽归一化（引擎自动处理，写 pattern 用正常字符即可）。
  - `fast=True` 只跑文本层（keyword+regex），语义层不执行——流式逐帧门禁靠它。
  - semantic 规则必须含 id/name/action/severity 四字段，否则 _compile_rules 剔除。
- 规则 id 命名：新增 R008-R011（R999 已保留给 AI 审核异常，不可占用）。
- 22 项清单以公开报道枚举的 19 条为准做矩阵；官方口径"22 项"的差异条目待正式文本全文发布后由合规部补录——矩阵文档必须写明此注（不许声称全覆盖）。
- 本机 DASHSCOPE_API_KEY 已配（测试环境语义层会真调 LLM）——文本层规则测试用 `fast=True` 跳过语义层，不真烧 token。

## 设计决策（执行前必读）

1. **可拦截 vs 流程管控两分法**（本计划的正确形态）：22 项里只有发生在"对话/内容"里的行为能靠三层审核拦截；主体/流程类（未备案、销售任务、机构/药企/CSO 责任条款）映射到平台管控点并在矩阵中标注状态，不硬造规则。
2. **条文来源**：2026-05 七部门发布《医药代表管理办法》，代表 9 种禁止性情形 + 机构 5 种 + 药企 3 项 + CSO 2 项（公开报道枚举 19 条）。
3. **规则粒度**：R008 附加销售条件利益输送（regex）、R009 馈赠财物（keyword）、R010 隐匿不良反应（keyword）、R011 误导用药（semantic）；R006 仅更新 description（收集/使用/传播口径），不改动 semantic 判断逻辑；R002 不动（回扣暗示已覆盖，财物类归 R009）。
4. **不新增 DB 列**：条文出处写进 rule description 尾部（"（2026《医药代表管理办法》）"），完整条文映射在矩阵文档。
5. **机构 5 项 / 药企 / CSO**：平台外主体，承接方式 = 审计留痕 + 监管自查报告导出（已有 3 Sheet xlsx），矩阵标注"已承接（报告）"，不新增功能。

## File Structure

- Modify: `shared/compliance-rules/rules.yaml` — 新增 R008-R011 + R006 description 更新
- Create: `scripts/migrations/010_seed_compliance_2026_rules.sql`
- Modify: `scripts/init_db.sql` — compliance_rules 种子块追加 4 行 + R006 描述同步
- Create: `services/compliance-service/tests/test_2026_rules.py`
- Create: `docs/compliance-2026-22items-matrix.md`
- Modify: `CLAUDE.md` — Compliance Rules 表 + 测试基线 + 矩阵文档链接

---

### Task 1: rules.yaml 新增规则 + 迁移 010 + init_db.sql 同步

**Files:**
- Modify: `shared/compliance-rules/rules.yaml`
- Create: `scripts/migrations/010_seed_compliance_2026_rules.sql`
- Modify: `scripts/init_db.sql`

**Interfaces:**
- Produces: R008（regex/high/reject）、R009（keyword/high/reject）、R010（keyword/high/reject）、R011（semantic/high/reject）四条规则 + R006 description 新口径。Task 2/3/4/5 依赖。

- [ ] **Step 1: rules.yaml 新增规则**

修改 `shared/compliance-rules/rules.yaml`，在 R007 条目之后追加：

```yaml
  - id: "R008"
    name: "禁止附加销售条件利益输送"
    type: "regex"
    patterns:
      - "按(销量|销售额|处方量|金额|数量).{0,12}(赞助|捐赠|资助)"
      - "(赞助|捐赠|资助).{0,12}(按|以).{0,8}(销量|销售额|金额|数量)"
      - "(销量|销售额)(达标|达到).{0,12}(赞助|捐赠|资助)"
    severity: "high"
    action: "reject"
    description: "禁止以附加销售药品金额、数量等条件提供捐赠、资助、赞助（2026《医药代表管理办法》）"
    enabled: true

  - id: "R009"
    name: "禁止馈赠财物"
    type: "keyword"
    patterns:
      - "礼品"
      - "礼金"
      - "购物卡"
      - "消费卡"
      - "有价证券"
      - "送红包"
      - "宴请"
      - "安排旅游"
      - "报销差旅"
    severity: "high"
    action: "reject"
    description: "禁止给予礼品、礼金、消费卡（券）、有价证券等财物或安排宴请、旅游（2026《医药代表管理办法》）"
    enabled: true

  - id: "R010"
    name: "禁止隐匿不良反应"
    type: "keyword"
    patterns:
      - "没有副作用"
      - "零副作用"
      - "无不良反应"
      - "绝对安全"
      - "安全性完全没问题"
      - "不良反应不用"
      - "不提不良反应"
    severity: "high"
    action: "reject"
    description: "禁止隐匿药品已知不良反应信息或隐瞒医生反馈的不良反应（2026《医药代表管理办法》）"
    enabled: true

  - id: "R011"
    name: "禁止误导用药"
    type: "semantic"
    severity: "high"
    action: "reject"
    description: "禁止误导医生使用药品、干预或影响临床合理使用药品（2026《医药代表管理办法》）"
    enabled: true
```

同时把 R006 的 description 改为：

```yaml
    description: "禁止在对话中非法收集、使用和传播可识别的患者个人信息及医疗机构内部信息"
```

- [ ] **Step 2: 迁移 010**

创建 `scripts/migrations/010_seed_compliance_2026_rules.sql`（沿用 004 的 `\set ON_ERROR_STOP on` 与注释风格；**只碰 R006/R008-R011 五行**）：

```sql
-- 010_seed_compliance_2026_rules.sql
-- 2026《医药代表管理办法》（2026-08-01 施行）22 项禁止行为清单映射：
--   新增 R008-R011 + 更新 R006 description。完整 22 项映射矩阵见
--   docs/compliance-2026-22items-matrix.md。
--
-- 注意（同 004）：只插新增行/更新改动行，不回写其他规则 ——
--   运营修改以 DB 为源，回写会覆盖后台改动。幂等可重复执行。
--
-- 执行：
--   docker exec -i medagent-postgres psql -U medagent medagent \
--     < scripts/migrations/010_seed_compliance_2026_rules.sql

\set ON_ERROR_STOP on

BEGIN;

INSERT INTO compliance_rules (rule_code, rule_name, rule_type, content, severity, action, description, enabled)
VALUES
('R008', '禁止附加销售条件利益输送', 'regex',
 '{"patterns": ["按(销量|销售额|处方量|金额|数量).{0,12}(赞助|捐赠|资助)", "(赞助|捐赠|资助).{0,12}(按|以).{0,8}(销量|销售额|金额|数量)", "(销量|销售额)(达标|达到).{0,12}(赞助|捐赠|资助)"]}',
 'high', 'reject', '禁止以附加销售药品金额、数量等条件提供捐赠、资助、赞助（2026《医药代表管理办法》）', TRUE),

('R009', '禁止馈赠财物', 'keyword',
 '{"patterns": ["礼品", "礼金", "购物卡", "消费卡", "有价证券", "送红包", "宴请", "安排旅游", "报销差旅"]}',
 'high', 'reject', '禁止给予礼品、礼金、消费卡（券）、有价证券等财物或安排宴请、旅游（2026《医药代表管理办法》）', TRUE),

('R010', '禁止隐匿不良反应', 'keyword',
 '{"patterns": ["没有副作用", "零副作用", "无不良反应", "绝对安全", "安全性完全没问题", "不良反应不用", "不提不良反应"]}',
 'high', 'reject', '禁止隐匿药品已知不良反应信息或隐瞒医生反馈的不良反应（2026《医药代表管理办法》）', TRUE),

('R011', '禁止误导用药', 'semantic',
 '{}',
 'high', 'reject', '禁止误导医生使用药品、干预或影响临床合理使用药品（2026《医药代表管理办法》）', TRUE)
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name   = EXCLUDED.rule_name,
    rule_type   = EXCLUDED.rule_type,
    content     = EXCLUDED.content,
    severity    = EXCLUDED.severity,
    action      = EXCLUDED.action,
    description = EXCLUDED.description,
    enabled     = EXCLUDED.enabled,
    updated_at  = NOW();

UPDATE compliance_rules
SET description = '禁止在对话中非法收集、使用和传播可识别的患者个人信息及医疗机构内部信息（2026《医药代表管理办法》）',
    updated_at = NOW()
WHERE rule_code = 'R006';

COMMIT;
```

- [ ] **Step 3: init_db.sql 种子同步**

修改 `scripts/init_db.sql`：找到 compliance_rules 的种子 INSERT 块（R001-R007），追加与 Step 2 相同的 4 行 VALUES（R008-R011，保留 ON CONFLICT 子句不变）；R006 行在种子里的 description 同步为新口径。新环境建库即含全部规则。

- [ ] **Step 4: 验证 YAML 可解析 + 规则加载**

Run: `cd services/compliance-service && python -c "import yaml; d=yaml.safe_load(open('../../shared/compliance-rules/rules.yaml', encoding='utf-8')); rules=d['rules']; assert [r['id'] for r in rules] == ['R001','R002','R003','R004','R005','R006','R007','R008','R009','R010','R011']; print('OK', len(rules), 'rules')"`
Expected: `OK 11 rules`

- [ ] **Step 5: 提交**

```bash
git add shared/compliance-rules/rules.yaml scripts/migrations/010_seed_compliance_2026_rules.sql scripts/init_db.sql
git commit -m "feat(compliance): 2026 办法映射新增 R008-R011 规则 + 迁移 010

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 新规则命中测试

**Files:**
- Create: `services/compliance-service/tests/test_2026_rules.py`

**Interfaces:**
- Consumes: R008-R011 + R006 新描述（Task 1，YAML 种子）。
- Produces: 测试锁定：文本层命中语义、fast 跳过语义、DB 覆盖机制不破坏新规则。

- [ ] **Step 1: 写测试**

创建 `services/compliance-service/tests/test_2026_rules.py`（沿用 test_db_rules.py 的 `_FakeRow`/`_FakeDb` + monkeypatch SessionLocal 模式；文本层断言用 `fast=True` 跳过语义层，不真调 LLM）：

```python
"""2026《医药代表管理办法》映射新增规则测试（R008-R011 + R006 新口径）

文本层（keyword/regex）用 fast=True 断言命中 —— fast 只跑文本层，
语义层不执行，测试不依赖 DASHSCOPE_API_KEY、不烧 token。
"""
import pytest

from app.core.checker import ComplianceChecker


class _FakeDb:
    """空 DB：只吃 YAML 种子（新增规则已在 Task 1 写入 rules.yaml）"""

    def query(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def all(self):
        return []

    def close(self):
        pass


@pytest.fixture()
def checker(monkeypatch):
    monkeypatch.setattr("shared.common.db_session.SessionLocal", lambda: _FakeDb())
    return ComplianceChecker()


def test_new_rules_loaded_from_yaml(checker):
    ids = {r["id"] for r in checker.rules}
    assert {"R008", "R009", "R010", "R011"} <= ids
    r006 = next(r for r in checker.rules if r["id"] == "R006")
    assert "非法收集" in r006["description"]


def test_r008_regex_hits_sales_condition_sponsor(checker):
    result = checker.check("只要销量达到100盒，我们就给科室赞助", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R008" in codes


def test_r008_regex_hits_sponsor_first_order(checker):
    result = checker.check("公司赞助的前提是按销售额返点", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R008" in codes


def test_r009_keyword_hits_gift(checker):
    result = checker.check("下次拜访给您带点礼品", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R009" in codes


def test_r010_keyword_hits_hidden_adverse_effect(checker):
    result = checker.check("我们这个药没有副作用，绝对安全", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R010" in codes


def test_r011_semantic_not_executed_in_fast_mode(checker):
    result = checker.check("按说明书用药即可", fast=True)
    # 语义规则在 fast 模式不执行：checked_rules 不含 R011
    assert "R011" not in result["checked_rules"]
    # R011 已注册（normal 模式会执行）
    assert any(r["id"] == "R011" and r["type"] == "semantic" for r in checker.rules)


def test_existing_r002_still_hits_regression(checker):
    result = checker.check("这个药有返点吗", fast=True)
    codes = [v["rule_code"] for v in result["violations"]]
    assert "R002" in codes
```

- [ ] **Step 2: 运行测试验证通过**

Run: `cd services/compliance-service && python -m pytest tests/test_2026_rules.py -v`
Expected: 7 passed
（若 test_r008_regex_hits_sponsor_first_order 未命中：核对 regex pattern 与测试句子——"公司赞助的前提是按销售额返点"应命中第 2 条 `(赞助|捐赠|资助).{0,12}(按|以).{0,8}(销量|销售额|金额|数量)`；句子中间隔词较多时按 pattern 收紧测试句，语义保持不变。）

- [ ] **Step 3: 全量回归**

Run: `cd services/compliance-service && python -m pytest tests/ -q`
Expected: 104 passed（97 + 7）

- [ ] **Step 4: 提交**

```bash
git add services/compliance-service/tests/test_2026_rules.py
git commit -m "test(compliance): R008-R011 命中与 fast 跳过语义层用例

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 22 项全覆盖矩阵文档

**Files:**
- Create: `docs/compliance-2026-22items-matrix.md`

**Interfaces:**
- 无代码接口。产物供合规部/老板验收 + Task 5 的 CLAUDE.md 引用。

- [ ] **Step 1: 写矩阵文档**

创建 `docs/compliance-2026-22items-matrix.md`（内容如下，逐字照抄）：

````markdown
# 2026《医药代表管理办法》22 项禁止行为清单映射矩阵

> 依据：2026-05 七部门（国家药监局、公安部、国家卫健委、市场监管总局、国家医保局、国家中医药局、国家疾控局）联合发布《医药代表管理办法》，2026-08-01 起施行。
> **口径说明**：本矩阵以公开报道枚举的 19 条禁止行为为条目；官方口径为"22 项"，与报道枚举的差异条目待正式文本全文发布后由合规部补录，**本矩阵不声称全覆盖**。

## 一、医药代表 9 种禁止性情形

| # | 禁止行为 | 平台承接 | 状态 |
|---|---|---|---|
| 1 | 未经备案、登记从事药品学术推广活动 | 备案前置门禁：备案录入+人工审核+到期自动冻结（一期 A 已交付冻结/审核；"未备案禁用平台"全量门禁待老板拍板存量方案） | 部分承接（挂账） |
| 2 | 未经医疗卫生机构同意开展药品学术推广活动 | 拜访记录已有；机构授权台账待建（拜访前校验授权状态） | 挂账（新） |
| 3 | 承担药品销售任务，实施收款和处理购销票据等销售行为 | 平台功能边界：无销售/收款模块；统方数据零留存（需求文档第七章） | 已承接 |
| 4 | 参与统计医生个人开具的药品处方数量（统方） | 拦截规则 **R003 禁止统方**（semantic/reject，已有） | 已承接 |
| 5 | 以附加销售药品金额、数量等条件提供捐赠、资助、赞助，或变相输送利益，或给予礼品、礼金、消费卡（券）、有价证券等财物 | 拦截规则 **R008 禁止附加销售条件利益输送**（regex/reject，本计划新增） | 已承接 |
| 6 | 以任何名义、形式向医疗机构工作人员及其亲属等给予回扣、财物、宴请旅游 | 拦截规则 **R002 禁止回扣暗示**（regex/reject，已有）+ **R009 禁止馈赠财物**（keyword/reject，本计划新增） | 已承接 |
| 7 | 误导医生使用药品，夸大或误导疗效，隐匿药品已知不良反应信息或隐瞒医生反馈的不良反应信息 | 拦截规则 **R001 禁止承诺疗效**（keyword/reject，已有）+ **R010 禁止隐匿不良反应**（keyword/reject，本计划新增）+ **R011 禁止误导用药**（semantic/reject，本计划新增） | 已承接 |
| 8 | 非法收集、使用和传播患者信息以及医疗卫生机构内部信息 | 拦截规则 **R006 禁止泄露患者信息**（semantic/reject，本计划扩充描述口径） | 已承接 |
| 9 | 实施药品上市许可持有人授权之外药品的学术推广活动 | 知识库内容边界控制：文档挂载绑定治疗领域与适应症标签（需求 3.1(4)，已有）；产品授权台账待建 | 部分承接（挂账） |

## 二、医疗卫生机构及其工作人员 5 种禁止行为

| # | 禁止行为 | 平台承接 | 状态 |
|---|---|---|---|
| 10 | 与未经备案、登记的医药代表开展药品学术推广活动 | 平台外主体行为；备案状态可查（备案平台公众查询 2026-08-01 起开通）+ 审计留痕 | 已承接（报告） |
| 11 | 违反主管部门规定统计药品使用量 | 平台外主体行为；平台自身统方零留存 + 审计留痕 | 已承接（报告） |
| 12 | 接受以附加销售药品金额、数量等条件提供的捐赠、资助、赞助或变相利益、财物 | 平台外主体行为；监管自查报告导出（3 Sheet xlsx，已有）支撑举证 | 已承接（报告） |
| 13 | 工作人员及其亲属接受医药代表给予的回扣、捐赠、赞助、财物或宴请、旅游 | 平台外主体行为；同上 | 已承接（报告） |
| 14 | 法律、行政法规禁止的其他行为 | 兜底条款；同上 | 已承接（报告） |

## 三、药品上市许可持有人（药企）禁止行为

| # | 禁止行为 | 平台承接 | 状态 |
|---|---|---|---|
| 15 | 聘用或授权不符合条件、存在商业贿赂记录的医药代表 | 平台侧支撑：资质审核（学历/培训证明，一期 A 已交付）；商业贿赂记录核查依赖备案平台公示信息 | 部分承接（挂账） |
| 16 | 指使、纵容医药代表从事违法行为 | 平台外主体行为；审计留痕支撑举证 | 已承接（报告） |
| 17 | 向医药代表分配药品销售任务、要求实施收款等销售行为 | 平台功能边界：无销售任务/收款模块 | 已承接 |

## 四、受托专业组织（CSO）禁止行为

| # | 禁止行为 | 平台承接 | 状态 |
|---|---|---|---|
| 18 | 指使、纵容医药代表进行商业贿赂、诈骗等违法犯罪行为 | 平台外主体行为；审计留痕支撑举证 | 已承接（报告） |
| 19 | 指使、纵容医药代表违规开展药品学术推广活动 | 平台外主体行为；同上 | 已承接（报告） |

## 五、规则对照（本计划新增/更新）

| 规则码 | 规则名 | 类型 | 动作 | 覆盖条目 |
|---|---|---|---|---|
| R008 | 禁止附加销售条件利益输送 | regex | reject | 代表#5 |
| R009 | 禁止馈赠财物 | keyword | reject | 代表#6 |
| R010 | 禁止隐匿不良反应 | keyword | reject | 代表#7 |
| R011 | 禁止误导用药 | semantic | reject | 代表#7 |
| R006（更新描述） | 禁止泄露患者信息 | semantic | reject | 代表#8 |

执行口径：keyword/regex 在 fast（流式逐帧门禁）与 full 两条路径都生效；semantic 仅在 full 复核执行。所有新规则自动出现在移动端/代表端红线清单（/redlines）与监管自查报告导出中，无需额外接线。

## 六、挂账清单（本计划范围外，已同步 CLAUDE.md Known Gaps）

1. 未备案全量门禁（存量代表宽限方案待老板拍板）——一期 A 遗留。
2. 机构授权台账（拜访前校验授权状态）——待立项。
3. 产品授权台账（授权外药品推广的硬校验）——待立项。
4. 药企侧商业贿赂记录核查对接备案平台公示信息——待备案平台接口调研结论。
````

- [ ] **Step 2: 提交**

```bash
git add docs/compliance-2026-22items-matrix.md
git commit -m "docs: 2026 办法 22 项禁止行为映射矩阵

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 迁移 010 实跑 + 服务验证

**Files:**
- 无代码改动。验证用。

- [ ] **Step 1: 迁移 010 实跑（本地 Docker 库）**

先确认 Docker Desktop 运行（WSL 引擎），然后：

```bash
docker exec -i medagent-postgres psql -U medagent medagent \
  < scripts/migrations/010_seed_compliance_2026_rules.sql
docker exec medagent-postgres psql -U medagent medagent \
  -c "SELECT rule_code, rule_name, rule_type, action, enabled FROM compliance_rules ORDER BY rule_code;"
```

Expected: R001-R011 全表可见（R008-R011 enabled=t，R006 description 含"非法收集"）；重跑一次迁移验证幂等（无报错、行数不变）。

- [ ] **Step 2: 重启 compliance 服务并验证规则生效**

按 CLAUDE.md 的直跑方式重启 compliance-service（taskkill 旧 PID 后）：

```bash
cd services/compliance-service && python -m uvicorn app.main:app --port 8004
```

然后验证（用 python 发请求，中文 body 别用 git-bash curl）：

```python
import requests
r = requests.get("http://localhost:8004/health")
print(r.json())
r = requests.post("http://localhost:8004/api/v1/compliance/check",
                  json={"content": "只要销量达标就赞助科室会议", "service_name": "test", "fast": True},
                  headers={"X-Internal-Key": "<.env 的 INTERNAL_API_KEY>"})
print(r.json())
```

Expected: health ok；check 返回 blocked=true 且 violations 含 R008。再验证 /redlines（需要登录 token 走网关，或用服务直连带 Authorization）：

```python
r = requests.get("http://localhost:8004/api/v1/compliance/redlines",
                 headers={"Authorization": "Bearer <任意有效 token>"})
codes = [i["rule_code"] for i in r.json()["data"]["items"]]
print(codes)
```

Expected: 含 R008-R011，且 items 无 patterns/content 字段。

- [ ] **Step 3: 结果写入报告**

验证结果（含迁移前后 SELECT 输出原文）写入 `.superpowers/sdd/2026-08-17-compliance-22items/task-4-report.md`（本任务无代码提交，无 commit）。

---

### Task 5: CLAUDE.md 同步 + 全量回归 + 推送

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: CLAUDE.md 同步**

修改 `CLAUDE.md`：
1. Compliance Rules 章节的规则表追加 4 行（R008-R011：类型/动作/来源）；R006 行描述更新为"非法收集、使用和传播"口径。
2. 规则表之后加一行引用：`完整 22 项清单映射矩阵见 docs/compliance-2026-22items-matrix.md（可拦截 → 规则；流程类 → 平台管控点）。`
3. 测试基线行更新：compliance `97 → 104`（含 R008-R011 命中/fast 跳过 7 用例）。
4. Known Gaps 追加：机构授权台账、产品授权台账、药企商业贿赂记录核查（与矩阵文档第六节同口径 4 条中的新增 3 条）。

- [ ] **Step 2: 全量回归**

Run: `cd services/compliance-service && python -m pytest tests/ -q`
Expected: 104 passed
其余套件不受影响（本计划未动其他服务代码；不需要跑 auth/gateway/mobile/web，如不放心可跑 gateway 77 做参考）。

- [ ] **Step 3: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md 同步 22 项映射（R008-R011 + 矩阵链接 + 基线 104）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

- [ ] **Step 4: 推送（用户确认后）**

```bash
git push origin master   # origin = Codeup
```

---

## 附录：验收对照（22 项清单 → 本计划任务）

| 条目 | 落点 |
|---|---|
| 代表#1-#9 九种情形 | Task 1（规则）/ Task 3（矩阵）/ Task 4（实跑） |
| 机构 5 种 / 药企 3 项 / CSO 2 项 | Task 3 矩阵"已承接（报告）"行 |
| 规则种子三处同步（YAML/迁移/init_db） | Task 1 |
| 命中测试 + fast 语义 | Task 2 |
| 22 项矩阵文档 | Task 3 |
| 实跑 + /redlines 验证 | Task 4 |
| 文档同步 + 基线 + 推送 | Task 5 |
| 官方 22 项与报道 19 条差异条目 | 矩阵文档口径说明（合规部补录） |
