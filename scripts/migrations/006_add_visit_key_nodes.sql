-- 006_add_visit_key_nodes.sql
-- LLM 实时推荐（2026-08-11）落库列：AI 关键节点标记（决策点/兴趣点）+ 话术建议引用。
-- 数组元素形状：{"type": "decision_point|interest_point", "label": str, "quote": str,
--                "created_at": "ISO8601"}；无 AI 推荐时为 NULL。
--
-- 用法：
--   docker exec -i medagent-postgres psql -U medagent medagent \
--     < scripts/migrations/006_add_visit_key_nodes.sql
-- （ALTER TABLE 只需表 owner/应用账号；无 superuser 前置条件，与 002/005 不同）

\set ON_ERROR_STOP on

ALTER TABLE visit_records ADD COLUMN IF NOT EXISTS key_nodes JSONB;
