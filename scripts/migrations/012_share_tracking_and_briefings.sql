-- 012_share_tracking_and_briefings.sql
-- 一期 C：share_links 加 add_count（使用追踪）+ nightly_briefings 表（分身夜间简报）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/012_share_tracking_and_briefings.sql

\set ON_ERROR_STOP on

ALTER TABLE share_links ADD COLUMN IF NOT EXISTS add_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS nightly_briefings (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    specialist_id BIGINT NOT NULL REFERENCES digital_specialists(id),
    briefing_date DATE NOT NULL,
    content JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ready',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_nb_rep_spec_date UNIQUE (representative_id, specialist_id, briefing_date)
);

CREATE INDEX IF NOT EXISTS idx_nb_rep ON nightly_briefings(representative_id);
