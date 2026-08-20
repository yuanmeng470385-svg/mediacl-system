-- 019_skill_ecosystem.sql
-- 三期 J：Skill 生态闭环（代表发布内容字段 / 下架字段 / 下架记录）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/019_skill_ecosystem.sql

\set ON_ERROR_STOP on

ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS description VARCHAR(200);
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS content TEXT;
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_reason VARCHAR(500);
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_type VARCHAR(20);
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_by BIGINT REFERENCES users(id);
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS off_shelf_at TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_sp_off ON skill_packages(off_shelf_status);

CREATE TABLE IF NOT EXISTS skill_off_shelves (
    id BIGSERIAL PRIMARY KEY,
    skill_id BIGINT NOT NULL REFERENCES skill_packages(id),
    operator_id BIGINT NOT NULL REFERENCES users(id),
    off_shelf_type VARCHAR(20) NOT NULL,   -- compliance/author
    reason VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sos_skill ON skill_off_shelves(skill_id);
