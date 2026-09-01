-- 027：skill_packages 加 source_session_ids（2026-09-01 Skill 审核盲审修复批）
-- 记录陪练提取→发布链路的来源会话 ID 数组（1~10 个，发布时校验归属），
-- 供审核侧受控查看原始对话（溯源：核对摘录是否忠于本人原文）。存量行 NULL。
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS source_session_ids JSONB;
