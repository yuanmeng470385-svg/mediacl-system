-- 023_privacy_center.sql
-- 三期 L：隐私中心（需求 5.7/3.8(4)(5)）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/023_privacy_center.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS privacy_requests (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    request_type VARCHAR(20) NOT NULL,               -- view/correct/delete/export/account_delete
    status VARCHAR(20) NOT NULL DEFAULT 'pending',   -- pending/processing/done/rejected
    content JSONB,                                   -- {detail, fields:{full_name,phone}, confirm, response}
    sla_deadline TIMESTAMP NOT NULL,                 -- created_at + 30 自然日（API 层写入）
    handled_by BIGINT REFERENCES users(id),
    handled_at TIMESTAMP,
    file_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pr_doctor ON privacy_requests(doctor_id);
CREATE INDEX IF NOT EXISTS idx_pr_status ON privacy_requests(status);

-- 注销标记列（status 值域扩 'deleted'；物理删除不做，法务拍板）
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
