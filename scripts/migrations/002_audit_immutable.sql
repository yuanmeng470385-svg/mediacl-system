-- 002_audit_immutable.sql
-- 审计日志不可篡改落地（S3）：
--
--   init_db.sql 里的 `REVOKE UPDATE, DELETE ON audit_logs FROM medagent` 从未生效 ——
--   medagent 是表的 owner，PostgreSQL 中 owner 的权限来自 ownership，REVOKE 管不到。
--   本脚本做三层分离，"不可篡改"才真正生效：
--   - medagent_audit_owner（NOLOGIN，不用于连接）：表的 owner，仅作管理占位；
--   - medagent_audit（审计服务连接账号）：仅 INSERT/SELECT，无 UPDATE/DELETE/TRUNCATE；
--   - medagent（其余服务连接账号）：仅 SELECT（联查/报表），无法写、改、删审计记录。
--
-- 用法（密码通过 psql 变量传入，仓库不放默认口令）：
--   docker exec -i medagent-postgres psql -U medagent medagent \
--     -v audit_password='<强密码>' < scripts/migrations/002_audit_immutable.sql
--
-- 配套：audit-service 必须用 medagent_audit 账号连接（AUDIT_DATABASE_URL 环境变量），
-- 否则写审计会因无 INSERT 权限而静默失败。

\set ON_ERROR_STOP on

-- 1. 创建专用低权账号（已存在则跳过；\gexec 让 psql 变量在 format 中展开）
SELECT format('CREATE ROLE medagent_audit LOGIN PASSWORD %L', :'audit_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'medagent_audit')\gexec

-- 2. owner 改为不可连接的占位角色（不能直接让 medagent_audit 当 owner ——
--    owner 自带 UPDATE/DELETE，REVOKE 管不到）
SELECT 'CREATE ROLE medagent_audit_owner NOLOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'medagent_audit_owner')\gexec
ALTER TABLE audit_logs OWNER TO medagent_audit_owner;
ALTER SEQUENCE audit_logs_id_seq OWNER TO medagent_audit_owner;

-- 3. medagent_audit（审计服务连接账号）：仅 INSERT/SELECT
REVOKE ALL ON audit_logs FROM medagent_audit;
GRANT SELECT, INSERT ON audit_logs TO medagent_audit;
GRANT USAGE ON SEQUENCE audit_logs_id_seq TO medagent_audit;
-- 外键检查：写 audit_logs 时须验证 user_id 存在于 users —— 需要 REFERENCES/只读权限。
-- SELECT ON ALL TABLES：审计查询/报告导出会联查业务表（只读，不授予写权限）。
GRANT REFERENCES ON users TO medagent_audit;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO medagent_audit;

-- 4. medagent 账号只剩 SELECT：不能插、改、删、清空审计记录
REVOKE ALL ON audit_logs FROM medagent;
GRANT SELECT ON audit_logs TO medagent;

-- 5. medagent 降级为非 superuser —— PostgreSQL 官方镜像把 POSTGRES_USER 设为
--    superuser，而 superuser 无视 REVOKE（前几步的权限收紧对 superuser 无效）。
--    各业务表 owner 仍是 medagent，业务不受影响；只影响 audit_logs 的越权改写。
--    注意：只有 superuser 能执行本语句，且只需执行一次（幂等，可重跑）。
ALTER ROLE medagent NOSUPERUSER;
