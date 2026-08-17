-- 009_representative_qualifications.sql
-- 代表备案与资质表（需求文档 3.3/4.2/附录A，一期 A 计划）
--   - 备案状态 filing_status 是派生值不落库（not_filed/valid/expired 由
--     filing_number + filing_expire_date 计算，见 shared/models/qualification.py）
--   - compliance_training_completed / compliance_exam_score / commitment_signed
--     为二期培训考试预留列，本计划不接线
-- 用法：
--   docker exec -i medagent-postgres psql -U medagent medagent \
--     < scripts/migrations/009_representative_qualifications.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS representative_qualifications (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    education_cert VARCHAR(500) NOT NULL,
    training_cert VARCHAR(500),
    audit_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    filing_number VARCHAR(50),
    filing_expire_date DATE,
    reject_reason VARCHAR(500),
    reviewed_by BIGINT,
    reviewed_at TIMESTAMP,
    compliance_training_completed BOOLEAN NOT NULL DEFAULT FALSE,
    compliance_exam_score INTEGER,
    commitment_signed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qual_audit_status ON representative_qualifications(audit_status);
CREATE INDEX IF NOT EXISTS idx_qual_expire ON representative_qualifications(filing_expire_date);
