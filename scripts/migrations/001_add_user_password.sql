-- ============================================
-- 001 — users 表补齐登录所需字段
--
-- 背景：原 users 表没有任何存储凭证的列，导致登录接口无法实现。
-- 适用：已经用旧版 init_db.sql 建过库的环境。全新环境不需要跑，
--       init_db.sql 已包含这些定义。
--
-- 执行：
--   docker exec -i medagent-postgres psql -U medagent medagent \
--     < scripts/migrations/001_add_user_password.sql
-- ============================================

BEGIN;

-- 1. 密码哈希（bcrypt）。NULL 表示该用户未设置密码，禁止密码登录。
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

-- 2. 手机号唯一约束 —— 手机号验证码登录要求能唯一定位用户。
--    仅约束非空值：允许多个用户不填手机号。
--    若这一步报 duplicate key，说明库里已有重复手机号，需先人工去重。
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone ON users(phone) WHERE phone IS NOT NULL;

COMMIT;

-- 设置管理员密码：python scripts/seed_admin.py
