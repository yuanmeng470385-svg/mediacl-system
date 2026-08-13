-- 008_add_visit_status.sql
-- 拜访显式状态列（2026-08-12 修复 B3/B14）：
--   - 取消（cancel）需要持久化的显式状态 —— 此前业务状态完全从 ai_summary 推导，
--     "取消"无表意载体；
--   - completed / in_progress 语义仍从 ai_summary 推导（占位串 ≠ 已结束，可重试 end），
--     回填保证历史数据与新逻辑口径一致（与 app/constants.py 的占位串逐字一致）。
--
-- 用法：
--   docker exec -i medagent-postgres psql -U medagent medagent \
--     < scripts/migrations/008_add_visit_status.sql
-- （ALTER TABLE 只需表 owner/应用账号；无 superuser 前置条件，与 006 相同）

\set ON_ERROR_STOP on

ALTER TABLE visit_records ADD COLUMN IF NOT EXISTS status VARCHAR(20);

-- 回填：已有真实总结（非占位串）→ completed，否则 in_progress。
-- 取消状态无需回填 —— 取消是 008 之后才可能出现的新状态。
UPDATE visit_records
SET status = CASE
    WHEN ai_summary IS NOT NULL
         AND ai_summary <> '（AI 总结生成失败，拜访尚未结束，可重试结束拜访）'
        THEN 'completed'
    ELSE 'in_progress'
END
WHERE status IS NULL;

ALTER TABLE visit_records ALTER COLUMN status SET DEFAULT 'in_progress';
ALTER TABLE visit_records ALTER COLUMN status SET NOT NULL;
