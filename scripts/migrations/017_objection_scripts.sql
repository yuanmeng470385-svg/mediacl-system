-- 017_objection_scripts.sql
-- 二期 H 终审修复：异议话术库（需求 3.2(5)）——科室/性格/产品场景的医生异议话术 + 合规部审核 + 版本留痕
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/017_objection_scripts.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS objection_scripts (
    id BIGSERIAL PRIMARY KEY,
    scenario_type VARCHAR(50) NOT NULL,        -- 科室/性格/产品场景类型
    objection_content TEXT NOT NULL,           -- 医生异议话术
    response_guidance TEXT,                    -- 合规部审核的应对指引
    version VARCHAR(20) DEFAULT '1.0',
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/approved/rejected
    review_reason VARCHAR(500),
    reviewed_by BIGINT,
    created_by BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_os_scenario ON objection_scripts(scenario_type);
CREATE INDEX IF NOT EXISTS idx_os_status ON objection_scripts(review_status);
