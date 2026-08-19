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
    password_hash VARCHAR(255),             -- bcrypt；NULL = 未设置密码，禁止密码登录
    role VARCHAR(20) NOT NULL,              -- admin / manager / rep / compliance / medical / finance / doctor
    region VARCHAR(50),
    manager_id BIGINT REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_manager ON users(manager_id);
-- 手机号登录要求手机号唯一（仅约束非空值，允许多个用户不填手机号）
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone ON users(phone) WHERE phone IS NOT NULL;

-- 代表备案与资质表（迁移 009）
CREATE TABLE IF NOT EXISTS representative_qualifications (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    education_cert VARCHAR(500) NOT NULL,
    training_cert VARCHAR(500),
    audit_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    filing_number VARCHAR(50),
    filing_expire_date DATE,
    reject_reason VARCHAR(500),
    reviewed_by BIGINT,
    reviewed_at TIMESTAMP,
    compliance_training_completed BOOLEAN NOT NULL DEFAULT FALSE,
    compliance_exam_score INTEGER,
    commitment_signed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_qual_audit_status ON representative_qualifications(audit_status);
CREATE INDEX IF NOT EXISTS idx_qual_expire ON representative_qualifications(filing_expire_date);

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
    is_official BOOLEAN NOT NULL DEFAULT FALSE,
    representative_id BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_specialists_product ON digital_specialists(product_id);
CREATE INDEX IF NOT EXISTS idx_specialists_status ON digital_specialists(status);
CREATE INDEX IF NOT EXISTS idx_ds_official ON digital_specialists(is_official);

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
    status VARCHAR(20) NOT NULL DEFAULT 'in_progress',  -- 显式状态（迁移 008）：仅 cancelled 以此列为准，completed/in_progress 由 ai_summary 推导
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
    key_nodes JSONB,                       -- LLM 实时推荐：关键节点标记数组（迁移 006）
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
-- 注意：key_nodes / status 两列由迁移 006 / 008 引入 —— 旧库（早期版本 init_db.sql 建的表）
-- 不会因 CREATE TABLE IF NOT EXISTS 自动补列，仍须执行 scripts/migrations/006_add_visit_key_nodes.sql
-- 与 008_add_visit_status.sql（008 含状态回填）。
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
-- ⚠️ 注意：官方 postgres 镜像把 POSTGRES_USER（默认 medagent）创建为 superuser 且是
--     audit_logs 的 owner —— superuser/owner 的权限来自 superuser 属性/ownership，
--     REVOKE 对它们不生效，此句只是"声明意图"。
--     必须执行 scripts/migrations/002_audit_immutable.sql（一次性手动迁移，见该文件头部用法）
--     才能真正不可篡改：它创建 medagent_audit 低权账号、把表 owner 移交占位角色、
--     并将 medagent 降级为非 superuser。002 未执行前审计表仍可被 medagent 随意改写。
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

-- 管理员账号（password_hash 故意留空 —— 仓库里不放默认口令）
-- 设置密码：python scripts/seed_admin.py
INSERT INTO users (username, full_name, phone, role, status)
VALUES ('admin', '系统管理员', '13800000000', 'admin', 'active')
ON CONFLICT (username) DO NOTHING;

-- 示例产品
INSERT INTO products (product_code, product_name, generic_name, manufacturer, indication, status)
VALUES ('ONC-001', 'XX注射液', 'XXX注射用冻干粉', 'XX制药', '用于治疗XXX', 'active')
ON CONFLICT (product_code) DO NOTHING;

-- 初始合规规则 (R001-R011) —— 与 shared/compliance-rules/rules.yaml 完全一致
-- （compliance-service 加载时同 rule_code 以 DB 为准，故种子必须覆盖 YAML 全集，
--   否则 YAML 有而 DB 没有的拦截词会永久失效）
INSERT INTO compliance_rules (rule_code, rule_name, rule_type, content, severity, action, description)
VALUES
('R001', '禁止承诺疗效', 'keyword',
 '{"patterns": ["保证治好", "100%有效", "100% 有效", "吃了就好", "一定能治好", "包治百病", "绝对有效", "肯定能好", "百分之百", "药到病除"]}',
 'high', 'reject', '禁止对产品疗效做出绝对化承诺或保证'),

('R002', '禁止回扣暗示', 'regex',
 '{"patterns": ["返[点红]", "提成费", "好处费", "私下给", "给回[扣]", "酬[劳谢]"]}',
 'high', 'reject', '禁止暗示或讨论回扣、返点等利益输送行为'),

('R003', '禁止统方', 'semantic',
 '{}',
 'high', 'reject', '禁止询问或讨论医生处方量、处方数据'),

('R004', '禁止超适应症推广', 'semantic',
 '{}',
 'high', 'reject', '禁止推广超出国家药监局批准药品说明书范围的适应症'),

('R005', '禁止贬低竞品', 'semantic',
 '{}',
 'medium', 'warn', '禁止恶意贬低或诋毁竞品产品'),

('R006', '禁止泄露患者信息', 'semantic',
 '{}',
 'high', 'reject', '禁止在对话中非法收集、使用和传播可识别的患者个人信息及医疗机构内部信息（2026《医药代表管理办法》）'),

('R007', '禁止讨论未公开数据', 'semantic',
 '{}',
 'high', 'warn', '禁止讨论公司内部未公开的临床试验数据或商业信息'),

('R008', '禁止附加销售条件利益输送', 'regex',
 '{"patterns": ["按(销量|销售额|处方量|金额|数量).{0,12}(赞助|捐赠|资助)", "(赞助|捐赠|资助).{0,12}(按|以).{0,8}(销量|销售额|金额|数量)", "(销量|销售额)(达标|达到).{0,12}(赞助|捐赠|资助)"]}',
 'high', 'reject', '禁止以附加销售药品金额、数量等条件提供捐赠、资助、赞助（2026《医药代表管理办法》）'),

('R009', '禁止馈赠财物', 'keyword',
 '{"patterns": ["礼品", "礼金", "购物卡", "消费卡", "有价证券", "送红包", "宴请", "安排旅游", "报销差旅"]}',
 'high', 'reject', '禁止给予礼品、礼金、消费卡（券）、有价证券等财物或安排宴请、旅游（2026《医药代表管理办法》）'),

('R010', '禁止隐匿不良反应', 'keyword',
 '{"patterns": ["没有副作用", "零副作用", "无不良反应", "绝对安全", "安全性完全没问题", "不良反应不用", "不提不良反应"]}',
 'high', 'reject', '禁止隐匿药品已知不良反应信息或隐瞒医生反馈的不良反应（2026《医药代表管理办法》）'),

('R011', '禁止误导用药', 'semantic',
 '{}',
 'high', 'reject', '禁止误导医生使用药品（2026《医药代表管理办法》）')
ON CONFLICT (rule_code) DO NOTHING;

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

-- ============================================
-- 011 — 一期 B 医生端四表：医师认证 / 分身订阅 / 知情同意留痕 / 分享链接
-- 执行：docker exec -i medagent-postgres psql -U medagent medagent \
--          < scripts/migrations/011_doctor_platform.sql
-- 全新环境：init_db.sql 已同步包含以下定义，无需执行本脚本。
-- ============================================

CREATE TABLE IF NOT EXISTS doctor_certifications (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL UNIQUE REFERENCES users(id),
    cert_type VARCHAR(20) NOT NULL,
    cert_image_url VARCHAR(500) NOT NULL,
    cert_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reject_reason VARCHAR(500),
    reviewed_by BIGINT,
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS doctor_twin_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    twin_id BIGINT NOT NULL REFERENCES digital_specialists(id),
    status VARCHAR(20) NOT NULL DEFAULT 'subscribed',
    consent_version VARCHAR(20) NOT NULL,
    consent_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_doctor_twin UNIQUE (doctor_id, twin_id)
);

CREATE TABLE IF NOT EXISTS doctor_consents (
    id BIGSERIAL PRIMARY KEY,
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    twin_id BIGINT REFERENCES digital_specialists(id),
    consent_type VARCHAR(20) NOT NULL,
    version VARCHAR(20) NOT NULL,
    agreed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS share_links (
    id BIGSERIAL PRIMARY KEY,
    twin_id BIGINT NOT NULL REFERENCES digital_specialists(id),
    url_token VARCHAR(64) UNIQUE NOT NULL,
    created_by BIGINT NOT NULL REFERENCES users(id),
    expire_at TIMESTAMP,
    add_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dts_doctor ON doctor_twin_subscriptions(doctor_id);
CREATE INDEX IF NOT EXISTS idx_sl_token ON share_links(url_token);

CREATE TABLE IF NOT EXISTS nightly_briefings (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    specialist_id BIGINT NOT NULL REFERENCES digital_specialists(id),
    briefing_date DATE NOT NULL,
    content JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ready',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_nb_rep_spec_date UNIQUE (representative_id, specialist_id, briefing_date)
);

CREATE INDEX IF NOT EXISTS idx_nb_rep ON nightly_briefings(representative_id);

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
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_er_rep ON exam_records(representative_id);

CREATE TABLE IF NOT EXISTS academic_cards (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    content JSONB NOT NULL,              -- {conclusion, key_points[], summary, citations[]}
    is_ai_generated BOOLEAN NOT NULL DEFAULT TRUE,
    compliance_status VARCHAR(20) NOT NULL DEFAULT 'passed',  -- passed/blocked
    status VARCHAR(20) NOT NULL DEFAULT 'active',             -- active/archived
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ac_rep ON academic_cards(representative_id);

CREATE TABLE IF NOT EXISTS card_push_records (
    id BIGSERIAL PRIMARY KEY,
    representative_id BIGINT NOT NULL REFERENCES users(id),
    card_id BIGINT NOT NULL REFERENCES academic_cards(id),
    doctor_id BIGINT NOT NULL REFERENCES users(id),
    specialist_id BIGINT REFERENCES digital_specialists(id),  -- 该医生订阅的代表分身（推送时记录）
    read_status VARCHAR(20) NOT NULL DEFAULT 'unread',  -- unread/read/favorited/forwarded
    read_at TIMESTAMP,
    tracked_seconds INTEGER NOT NULL DEFAULT 0,
    feedback VARCHAR(500),                                -- useful/useless/追问文本
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_push UNIQUE (card_id, doctor_id)
);
CREATE INDEX IF NOT EXISTS idx_cpr_doctor ON card_push_records(doctor_id);
CREATE INDEX IF NOT EXISTS idx_cpr_rep ON card_push_records(representative_id);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    type VARCHAR(20) NOT NULL,            -- briefing_ready/card_feedback/card_question
    title VARCHAR(200) NOT NULL,
    content VARCHAR(1000),
    link VARCHAR(200),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read);
