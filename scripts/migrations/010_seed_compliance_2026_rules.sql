-- 010_seed_compliance_2026_rules.sql
-- 2026《医药代表管理办法》（2026-08-01 施行）22 项禁止行为清单映射：
--   新增 R008-R011 + 更新 R006 description。完整 22 项映射矩阵见
--   docs/compliance-2026-22items-matrix.md。
--
-- 注意（同 004）：只插新增行/更新改动行，不回写其他规则 ——
--   运营修改以 DB 为源，回写会覆盖后台改动。幂等可重复执行。
-- 注意：重跑本脚本会把 R008-R011 的 enabled 重置为 TRUE（运营禁用会被覆盖），同 004 行为。
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
 'high', 'reject', '禁止误导医生使用药品（2026《医药代表管理办法》）', TRUE)
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
