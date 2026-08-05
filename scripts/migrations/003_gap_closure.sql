-- ============================================
-- 003 — 缺口补齐：反馈/收藏/任务/知识反馈表 + 版本链列
-- 执行：docker exec -i medagent-postgres psql -U medagent medagent \
--          < scripts/migrations/003_gap_closure.sql
-- 全新环境：init_db.sql 已同步包含以下定义，无需执行本脚本。
-- ============================================

BEGIN;

CREATE TABLE IF NOT EXISTS conversation_feedback (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES conversations(id),
    user_id BIGINT REFERENCES users(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_feedback_conversation ON conversation_feedback(conversation_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON conversation_feedback(user_id);

CREATE TABLE IF NOT EXISTS conversation_favorites (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT REFERENCES conversations(id),
    user_id BIGINT REFERENCES users(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),
    question TEXT,
    answer TEXT,
    citations JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, conversation_id)
);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON conversation_favorites(user_id);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    visit_id BIGINT REFERENCES visit_records(id),
    user_id BIGINT REFERENCES users(id),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    task_type VARCHAR(50) DEFAULT 'follow_up',
    due_date DATE,
    channel VARCHAR(50),
    status VARCHAR(20) DEFAULT 'open',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_visit ON tasks(visit_id);

CREATE TABLE IF NOT EXISTS knowledge_feedback (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    query TEXT,
    doc_id VARCHAR(100),
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS revision INT DEFAULT 1;
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS parent_doc_id BIGINT REFERENCES knowledge_documents(id);

COMMIT;
