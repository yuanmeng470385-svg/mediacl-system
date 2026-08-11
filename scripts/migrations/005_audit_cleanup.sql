-- 005_audit_cleanup.sql
-- 审计日志保留天数清理落地（AUDIT_LOG_RETENTION_DAYS 生效，2026-08-11）：
--
--   002_audit_immutable.sql 把审计表做成不可篡改：应用账号 medagent_audit
--   只有 INSERT/SELECT（连 DELETE 都没有），表 owner 是 NOLOGIN 占位角色。
--   但"保留天数"清理需要删除能力 —— 本脚本把删除权限单独授予专职维护账号
--   medagent_audit_cleanup（仅 SELECT+DELETE，无 INSERT/UPDATE/TRUNCATE），
--   与不可篡改语义共存：审计写入方永远没有删除权，只有维护账号能删过期数据。
--
-- 前置条件（必须）：
--   002 执行后系统无 superuser，而 GRANT DELETE 需要表 owner 或 superuser。
--   请先用 superuser 执行（002 头部建议保留的 medagent_root）：
--     CREATE ROLE medagent_root LOGIN SUPERUSER PASSWORD '<强密码>';   -- 若从未保留
--   若没有 superuser：本脚本的 GRANT 一步会报权限错误，需先造一个。
--
-- 用法（密码通过 psql 变量传入，仓库不放默认口令）：
--   docker exec -i medagent-postgres psql -U medagent_root medagent \
--     -v cleanup_password='<强密码>' < scripts/migrations/005_audit_cleanup.sql
--
-- 配套：audit-service 环境变量 AUDIT_CLEANUP_DATABASE_URL 指向该账号，例如
--   postgresql://medagent_audit_cleanup:<密码>@<host>:5432/medagent
-- 清理任务在 audit-service 启动时（及每 AUDIT_LOG_CLEANUP_INTERVAL_HOURS 小时）
-- 分批删除 timestamp < utcnow() - AUDIT_LOG_RETENTION_DAYS 的审计行。

\set ON_ERROR_STOP on

-- 1. 创建删除专用维护账号（已存在则跳过；\gexec 让 psql 变量在 format 中展开）
SELECT format('CREATE ROLE medagent_audit_cleanup LOGIN PASSWORD %L', :'cleanup_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'medagent_audit_cleanup')\gexec

-- 2. 仅授予 SELECT + DELETE（无 INSERT/UPDATE/TRUNCATE —— 不是审计写入方，
--    只能查和删过期数据，不能伪造/修改记录）
GRANT SELECT, DELETE ON audit_logs TO medagent_audit_cleanup;
