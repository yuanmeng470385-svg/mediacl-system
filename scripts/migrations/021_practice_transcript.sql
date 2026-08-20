-- 021_practice_transcript.sql
-- 三期 N：陪练对话逐轮落库（LLM 深度评分用，需求 4.5(4)）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/021_practice_transcript.sql

\set ON_ERROR_STOP on

ALTER TABLE practice_sessions ADD COLUMN IF NOT EXISTS transcript JSONB;
