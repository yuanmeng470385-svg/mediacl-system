-- 018_doctor_experience.sql
-- 二期 I：医生偏好画像 / 患教模板 / 患教内容（需求 5.4/5.5/3.9(2)/附录A）
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/018_doctor_experience.sql

\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS doctor_profiles (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    interest_areas JSONB,            -- ["心血管", "肿瘤"] 关注的疾病领域
    preferred_doc_type VARCHAR(50),  -- guideline/rct/real_world/case_report
    preferred_style VARCHAR(50),     -- 简洁/标准/详尽
    closed BOOLEAN NOT NULL DEFAULT FALSE,  -- 关闭个性化推荐
    updated_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dp_doctor ON doctor_profiles(doctor_id);

CREATE TABLE IF NOT EXISTS patient_edu_templates (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    disease_area VARCHAR(100) NOT NULL,   -- 心血管/肿瘤/内分泌/呼吸/神经
    content TEXT NOT NULL,                -- 模板正文（通俗语言）
    version VARCHAR(20) DEFAULT '1.0',
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/approved/rejected
    review_reason VARCHAR(500),
    reviewed_by BIGINT,
    created_by BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pet_disease ON patient_edu_templates(disease_area);
CREATE INDEX IF NOT EXISTS idx_pet_status ON patient_edu_templates(review_status);

CREATE TABLE IF NOT EXISTS edu_content_records (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    template_id BIGINT REFERENCES patient_edu_templates(id),
    content JSONB NOT NULL,           -- {title, body, notes, seek_care}
    is_ai_generated BOOLEAN NOT NULL DEFAULT TRUE,
    visibility VARCHAR(20) NOT NULL DEFAULT 'private',  -- private/shared
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ecr_doctor ON edu_content_records(doctor_id);
