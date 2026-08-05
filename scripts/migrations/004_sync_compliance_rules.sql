-- ============================================
-- 004 — 合规规则与 rules.yaml 全量对齐（幂等同步）
--
-- 背景：init_db.sql 旧种子只有 R001-R004，且 R001/R002 的 patterns 是
--       shared/compliance-rules/rules.yaml 的子集；而 compliance-service 的
--       加载逻辑是"同 rule_code 以 DB 为准"（DB 覆盖 YAML），导致 YAML 有而
--       DB 没有的拦截词（如 绝对有效/肯定能好/百分之百/药到病除 等）永久失效。
-- 本脚本把 compliance_rules 表与 rules.yaml 的完整规则集（R001-R007，
--   含全部 patterns/severity/action/description/enabled）逐条对齐，幂等可重复执行。
--
-- 注意：一次性同步，执行后如需修改规则请走管理后台（DB 为源）。
--       不要回改 rules.yaml 后再跑本脚本 —— 会把后台改动覆盖回 YAML 初始值。
--
-- 适用：已用旧版 init_db.sql 建过库的环境。全新环境 init_db.sql 已同步包含。
--
-- 执行：
--   docker exec -i medagent-postgres psql -U medagent medagent \
--     < scripts/migrations/004_sync_compliance_rules.sql
-- ============================================

BEGIN;

INSERT INTO compliance_rules (rule_code, rule_name, rule_type, content, severity, action, description, enabled)
VALUES
('R001', '禁止承诺疗效', 'keyword',
 '{"patterns": ["保证治好", "100%有效", "100% 有效", "吃了就好", "一定能治好", "包治百病", "绝对有效", "肯定能好", "百分之百", "药到病除"]}',
 'high', 'reject', '禁止对产品疗效做出绝对化承诺或保证', TRUE),

('R002', '禁止回扣暗示', 'regex',
 '{"patterns": ["返[点红]", "提成费", "好处费", "私下给", "给回[扣]", "酬[劳谢]"]}',
 'high', 'reject', '禁止暗示或讨论回扣、返点等利益输送行为', TRUE),

('R003', '禁止统方', 'semantic',
 '{}',
 'high', 'reject', '禁止询问或讨论医生处方量、处方数据', TRUE),

('R004', '禁止超适应症推广', 'semantic',
 '{}',
 'high', 'reject', '禁止推广超出国家药监局批准药品说明书范围的适应症', TRUE),

('R005', '禁止贬低竞品', 'semantic',
 '{}',
 'medium', 'warn', '禁止恶意贬低或诋毁竞品产品', TRUE),

('R006', '禁止泄露患者信息', 'semantic',
 '{}',
 'high', 'reject', '禁止在对话中提及可识别的患者个人信息', TRUE),

('R007', '禁止讨论未公开数据', 'semantic',
 '{}',
 'high', 'warn', '禁止讨论公司内部未公开的临床试验数据或商业信息', TRUE)
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name   = EXCLUDED.rule_name,
    rule_type   = EXCLUDED.rule_type,
    content     = EXCLUDED.content,
    severity    = EXCLUDED.severity,
    action      = EXCLUDED.action,
    description = EXCLUDED.description,
    enabled     = EXCLUDED.enabled,
    updated_at  = NOW();

COMMIT;
