-- 013_training_exam.sql
-- 二期 F：培训材料 / 题库 / 考试记录（需求文档 3.4/附录A）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/013_training_exam.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS training_materials (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    material_type VARCHAR(20) NOT NULL,      -- regulation(办法) / rdpac / internal(内部政策)
    content TEXT NOT NULL,
    version VARCHAR(20) DEFAULT '1.0',
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active / archived
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tm_type ON training_materials(material_type);
CREATE INDEX IF NOT EXISTS idx_tm_status ON training_materials(status);

CREATE TABLE IF NOT EXISTS exam_questions (
    id BIGSERIAL PRIMARY KEY,
    material_id BIGINT REFERENCES training_materials(id),
    question_type VARCHAR(10) NOT NULL,      -- single / multiple / judge
    content TEXT NOT NULL,
    options JSONB NOT NULL,                  -- ["选项A",...]（judge 为 ["正确","错误"]）
    answer JSONB NOT NULL,                   -- [i] 或 [i,j]；任何接口不对代表端返回
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending / approved / rejected
    review_reason VARCHAR(500),
    reviewed_by BIGINT,
    reviewed_at TIMESTAMP,
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eq_status ON exam_questions(review_status);
CREATE INDEX IF NOT EXISTS idx_eq_material ON exam_questions(material_id);

CREATE TABLE IF NOT EXISTS exam_records (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    question_count INTEGER NOT NULL,
    correct_count INTEGER NOT NULL,
    score INTEGER NOT NULL,
    passed BOOLEAN NOT NULL,
    submitted_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_er_rep ON exam_records(representative_id);
