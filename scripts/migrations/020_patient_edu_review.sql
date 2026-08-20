-- 020_patient_edu_review.sql
-- 三期 M：患教内容审核流（分享到专区审核，需求 5.5(3)/附录A）
-- NULL=未分享；分享→pending；审核→approved/rejected
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/020_patient_edu_review.sql

\set ON_ERROR_STOP on

ALTER TABLE edu_content_records ADD COLUMN IF NOT EXISTS audit_status VARCHAR(20);
CREATE INDEX IF NOT EXISTS idx_ecr_audit ON edu_content_records(audit_status);
