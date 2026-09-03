-- 028 患教转发留痕（2026-09-03 业务审查批）
-- 患教卡片站外转发此前是前端假 Alert（无留痕、无计数）；医生端 Share 唤起系统
-- 分享后回写本表。站外转发仍不经审核流（三期 M 拍板口径），只做记录。
ALTER TABLE edu_content_records
    ADD COLUMN IF NOT EXISTS forward_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_forwarded_at TIMESTAMP;
