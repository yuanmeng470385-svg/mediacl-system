-- 022_export_requests.sql
-- 三期 K：敏感数据导出审批（需求 3.8(3)）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/022_export_requests.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS export_requests (
    id BIGSERIAL PRIMARY KEY,
    requester_id BIGINT NOT NULL REFERENCES users(id),
    export_type VARCHAR(50) NOT NULL DEFAULT 'conversations',  -- conversations（一期唯一敏感导出物）
    reason VARCHAR(500),                                      -- 导出目的
    status VARCHAR(20) NOT NULL DEFAULT 'pending',            -- pending/approved/rejected
    approver_id BIGINT REFERENCES users(id),
    approve_reason VARCHAR(500),
    file_url VARCHAR(500),
    expires_at TIMESTAMP,
    responded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_er_status ON export_requests(status);
CREATE INDEX IF NOT EXISTS idx_er_requester ON export_requests(requester_id);
