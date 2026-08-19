-- 014_specialist_official.sql
-- 二期 E：digital_specialists 加 官方公共数字员工标识 + 归属代表（需求 3.5(4) 官方公共数字员工 / 4.3 个人分身）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/014_specialist_official.sql

\set ON_ERROR_STOP on

ALTER TABLE digital_specialists ADD COLUMN IF NOT EXISTS is_official BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE digital_specialists ADD COLUMN IF NOT EXISTS representative_id BIGINT REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_ds_official ON digital_specialists(is_official);
