-- ============================================
-- MedAgent 数字员工系统 - 数据库初始化
-- ============================================

-- 1. 用户表
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(100),
    role VARCHAR(20) NOT NULL,              -- admin / manager / rep / compliance / medical / finance
    region VARCHAR(50),
    manager_id BIGINT REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_manager ON users(manager_id);

-- 2. 产品表
CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    product_code VARCHAR(50) UNIQUE NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    generic_name VARCHAR(200),
    manufacturer VARCHAR(200),
    indication TEXT,
    approval_date DATE,
    status VARCHAR(20) DEFAULT 'active',
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3. 数字专员表
CREATE TABLE IF NOT EXISTS digital_specialists (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    product_id BIGINT REFERENCES products(id),
    persona JSONB,
    knowledge_scope JSONB,
    compliance_level VARCHAR(20) DEFAULT 'internal',
    bailian_app_id VARCHAR(100),
    prompt_version VARCHAR(20),
    status VARCHAR(20) DEFAULT 'draft',     -- draft / intern / active / disabled
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_specialists_product ON digital_specialists(product_id);
CREATE INDEX IF NOT EXISTS idx_specialists_status ON digital_specialists(status);

-- 4. 医生档案表 (HCP = Health Care Professional)
CREATE TABLE IF NOT EXISTS hcps (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    hospital VARCHAR(200),
    department VARCHAR(100),
    title VARCHAR(50),
    specialty VARCHAR(100),
    phone VARCHAR(20),
    email VARCHAR(100),
    region VARCHAR(50),
    academic_background JSONB,
    prescription_preference JSONB,
    influence_level VARCHAR(20),
    tags JSONB,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hcps_hospital ON hcps(hospital);
CREATE INDEX IF NOT EXISTS idx_hcps_department ON hcps(department);
CREATE INDEX IF NOT EXISTS idx_hcps_region ON hcps(region);

-- 5. 拜访记录表
CREATE TABLE IF NOT EXISTS visit_records (
    id BIGSERIAL PRIMARY KEY,
    hcp_id BIGINT REFERENCES hcps(id),
    user_id BIGINT REFERENCES users(id),
    product_id BIGINT REFERENCES products(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),
    visit_time TIMESTAMP NOT NULL,
    duration_minutes INT,
    conversation_transcript TEXT,
    ai_summary TEXT,
    key_points JSONB,
    hcp_interests JSONB,
    hcp_objections JSONB,
    follow_up_suggestions JSONB,
    sentiment VARCHAR(20),                 -- positive / neutral / negative
    compliance_flags JSONB,
    next_visit_plan JSONB,
    attachments JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_visits_hcp ON visit_records(hcp_id);
CREATE INDEX IF NOT EXISTS idx_visits_user ON visit_records(user_id);
CREATE INDEX IF NOT EXISTS idx_visits_time ON visit_records(visit_time);

-- 6. 对话记录表
CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),
    session_id VARCHAR(100),
    role VARCHAR(20) NOT NULL,              -- user / assistant
    content TEXT NOT NULL,
    citations JSONB,
    compliance_result JSONB,
    tokens_used INT,
    latency_ms INT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);

-- 7. 知识库文档表
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    doc_type VARCHAR(50) NOT NULL,          -- product / guideline / literature / regulation / competitor
    source VARCHAR(200),
    content TEXT,
    file_url VARCHAR(500),
    product_id BIGINT REFERENCES products(id),
    evidence_level VARCHAR(20),             -- A / B / C / expert_opinion / unknown
    publish_date DATE,
    version VARCHAR(20),
    status VARCHAR(20) DEFAULT 'draft',     -- draft / processing / ready / rejected
    reviewer_id BIGINT REFERENCES users(id),
    review_date TIMESTAMP,
    tags JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_product ON knowledge_documents(product_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_status ON knowledge_documents(status);

-- 8. 审计日志表（不可篡改）
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    service_name VARCHAR(50) NOT NULL,
    user_id BIGINT REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    before_value JSONB,
    after_value JSONB,
    ai_involved BOOLEAN DEFAULT FALSE,
    ai_model VARCHAR(50),
    ai_prompt_hash VARCHAR(100),
    ai_response_hash VARCHAR(100),
    compliance_result JSONB,
    risk_level VARCHAR(20),
    client_ip VARCHAR(50),
    user_agent TEXT,
    request_id VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_service ON audit_logs(service_name);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
-- 不可篡改：禁止 UPDATE 和 DELETE
REVOKE UPDATE, DELETE ON audit_logs FROM medagent;

-- 9. 合规规则表
CREATE TABLE IF NOT EXISTS compliance_rules (
    id BIGSERIAL PRIMARY KEY,
    rule_code VARCHAR(50) UNIQUE NOT NULL,
    rule_name VARCHAR(200) NOT NULL,
    rule_type VARCHAR(50) NOT NULL,         -- keyword / regex / semantic
    content JSONB NOT NULL,
    severity VARCHAR(20) DEFAULT 'high',    -- high / medium / low
    action VARCHAR(20) DEFAULT 'reject',    -- reject / warn / log
    description TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    version INT DEFAULT 1,
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_compliance_enabled ON compliance_rules(enabled);

-- 10. 合规拦截记录表
CREATE TABLE IF NOT EXISTS compliance_blocks (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    service_name VARCHAR(50),
    content TEXT,
    rule_code VARCHAR(50),
    rule_name VARCHAR(200),
    severity VARCHAR(20),
    action VARCHAR(20),
    context JSONB,
    blocked_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_compliance_blocks_user ON compliance_blocks(user_id);
CREATE INDEX IF NOT EXISTS idx_compliance_blocks_time ON compliance_blocks(blocked_at);

-- ==================== 种子数据 ====================

-- 管理员账号 (密码: admin123, 实际应使用 hash)
INSERT INTO users (username, full_name, role, status)
VALUES ('admin', '系统管理员', 'admin', 'active')
ON CONFLICT (username) DO NOTHING;

-- 示例产品
INSERT INTO products (product_code, product_name, generic_name, manufacturer, indication, status)
VALUES ('ONC-001', 'XX注射液', 'XXX注射用冻干粉', 'XX制药', '用于治疗XXX', 'active')
ON CONFLICT (product_code) DO NOTHING;

-- 初始合规规则 (R001-R004)
INSERT INTO compliance_rules (rule_code, rule_name, rule_type, content, severity, action, description)
VALUES
('R001', '禁止承诺疗效', 'keyword',
 '{"patterns": ["保证治好", "100%有效", "100% 有效", "吃了就好", "一定能治好", "包治百病"]}',
 'high', 'reject', '禁止对产品疗效做出绝对化承诺'),

('R002', '禁止回扣暗示', 'regex',
 '{"patterns": ["返[点红]", "提成费", "好处费", "私下给", "给回[扣]"]}',
 'high', 'reject', '禁止暗示或讨论回扣、返点等利益输送'),

('R003', '禁止统方', 'semantic',
 '{}',
 'high', 'reject', '禁止询问或讨论医生处方量数据'),

('R004', '禁止超适应症推广', 'semantic',
 '{}',
 'high', 'reject', '禁止推广超出药品说明书范围的适应症')
ON CONFLICT (rule_code) DO NOTHING;
