-- 011_doctor_platform.sql
-- 一期 B 医生端四表：医师认证 / 分身订阅 / 知情同意留痕 / 分享链接（B 建表，C 做生成侧）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/011_doctor_platform.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS doctor_certifications (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    cert_type VARCHAR(20) NOT NULL,
    cert_image_url VARCHAR(500) NOT NULL,
    cert_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reject_reason VARCHAR(500),
    reviewed_by BIGINT,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS doctor_twin_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    twin_id BIGINT NOT NULL REFERENCES digital_specialists(id),
    status VARCHAR(20) NOT NULL DEFAULT 'subscribed',
    consent_version VARCHAR(20) NOT NULL,
    consent_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_doctor_twin UNIQUE (doctor_id, twin_id)
);

CREATE TABLE IF NOT EXISTS doctor_consents (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    twin_id BIGINT REFERENCES digital_specialists(id),
    consent_type VARCHAR(20) NOT NULL,
    version VARCHAR(20) NOT NULL,
    agreed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS share_links (
    id BIGSERIAL PRIMARY KEY,
    twin_id BIGINT NOT NULL REFERENCES digital_specialists(id),
    url_token VARCHAR(64) UNIQUE NOT NULL,
    created_by BIGINT NOT NULL REFERENCES users(id),
    expire_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dts_doctor ON doctor_twin_subscriptions(doctor_id);
CREATE INDEX IF NOT EXISTS idx_sl_token ON share_links(url_token);
