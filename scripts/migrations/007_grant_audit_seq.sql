-- 007_grant_audit_seq.sql
-- 修复 medagent 对 audit_logs_id_seq 的 sequence 权限（备份链路发现）：
--
--   002_audit_immutable.sql 只授了 medagent 对表 audit_logs 的 SELECT，
--   没授 sequence —— pg_dump -Fc 全量备份会触碰 sequence 并失败：
--       permission denied for sequence audit_logs_id_seq
--   （scripts/backup_db.py 每日 02:00 备份在 ECS 上必挂，执行本迁移后方可。）
--
-- 用法（必须以 medagent_root 等 superuser 执行：medagent 在 002 后已 NOSUPERUSER，
-- 且 sequence owner 是 medagent_audit_owner，GRANT 需要 superuser）：
--   docker exec -i medagent-postgres psql -U medagent_root -d medagent \
--     < scripts/migrations/007_grant_audit_seq.sql
--
-- 幂等可重跑。
\set ON_ERROR_STOP on
GRANT SELECT, USAGE ON SEQUENCE public.audit_logs_id_seq TO medagent;
