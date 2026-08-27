-- 026_card_push_matched_interest.sql
-- 学术偏好接入（2026-08-27 spec）：推送记录标兴趣匹配（matched_interest）
-- 可空：历史推送不填充，仅新推送写入；不改变推送行为、不丢触达。
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/026_card_push_matched_interest.sql

\set ON_ERROR_STOP on

ALTER TABLE card_push_records ADD COLUMN matched_interest BOOLEAN NULL;
