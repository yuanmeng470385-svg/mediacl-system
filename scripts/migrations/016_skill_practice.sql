-- 016_skill_practice.sql
-- 二期 H：Skill 模版 / Skill 审核 / 陪练会话（需求 3.6/4.5/附录A skill_packages/skill_audits）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/016_skill_practice.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS skill_packages (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    creator_id BIGINT REFERENCES users(id),
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    is_anonymous BOOLEAN NOT NULL DEFAULT FALSE,
    audit_status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/approved/rejected
    audit_reason VARCHAR(500),
    style_tags JSONB,          -- ["严谨学术", "亲和力"] 等（元数据，公共列表展示）
    heat INTEGER NOT NULL DEFAULT 0,          -- 加载热度
    approval_rate DECIMAL(5,4),              -- 好评率（陪练评分汇总）
    skill_weights JSONB,       -- 沟通风格参数（正式度/回复长度/开场白）—— 任何 API 不返回
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sp_public ON skill_packages(is_public, audit_status);
CREATE INDEX IF NOT EXISTS idx_sp_tags ON skill_packages(style_tags);

CREATE TABLE IF NOT EXISTS skill_audits (
    id BIGSERIAL PRIMARY KEY,
    skill_id BIGINT NOT NULL REFERENCES skill_packages(id),
    auditor_id BIGINT NOT NULL REFERENCES users(id),
    audit_result VARCHAR(20) NOT NULL,       -- approved/rejected
    reason VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sa_skill ON skill_audits(skill_id);

CREATE TABLE IF NOT EXISTS practice_sessions (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    skill_id BIGINT REFERENCES skill_packages(id),
    scenario VARCHAR(100),                   -- 科室/性格/产品场景描述
    status VARCHAR(20) NOT NULL DEFAULT 'in_progress',  -- in_progress/completed
    scores JSONB,                            -- 评分 {evidence_accuracy, objection_handling, communication_logic, overall}
    turn_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ps_rep ON practice_sessions(representative_id);
