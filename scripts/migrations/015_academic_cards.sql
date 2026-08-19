-- 015_academic_cards.sql
-- 二期 G：学术卡片 / 卡片推送记录 / 站内通知（需求 4.6/5.3/6.3/3.7(1)）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/015_academic_cards.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS academic_cards (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    content JSONB NOT NULL,              -- {conclusion, key_points[], summary, citations[]}
    is_ai_generated BOOLEAN NOT NULL DEFAULT TRUE,
    compliance_status VARCHAR(20) NOT NULL DEFAULT 'passed',  -- passed/blocked
    status VARCHAR(20) NOT NULL DEFAULT 'active',             -- active/archived
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ac_rep ON academic_cards(representative_id);

CREATE TABLE IF NOT EXISTS card_push_records (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    card_id BIGINT NOT NULL REFERENCES academic_cards(id),
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    read_status VARCHAR(20) NOT NULL DEFAULT 'unread',  -- unread/read/favorited/forwarded
    read_at TIMESTAMP,
    tracked_seconds INTEGER NOT NULL DEFAULT 0,
    feedback VARCHAR(500),                                -- useful/useless/追问文本
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_push UNIQUE (card_id, doctor_id)
);
CREATE INDEX IF NOT EXISTS idx_cpr_doctor ON card_push_records(doctor_id);
CREATE INDEX IF NOT EXISTS idx_cpr_rep ON card_push_records(representative_id);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    type VARCHAR(20) NOT NULL,            -- briefing_ready/card_feedback/card_question
    title VARCHAR(200) NOT NULL,
    content VARCHAR(1000),
    link VARCHAR(200),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read);
