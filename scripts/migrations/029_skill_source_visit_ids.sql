-- 029：Skill 发布溯源支持拜访对话（2026-09-10 老板需求）
-- extract-draft / release 的素材源从「仅陪练会话」扩展到「陪练 + 拜访对话」，
-- 与 source_session_ids（迁移 027）同构：审核人受控查看（GET /skill-packages/source-visits/{id}）。
ALTER TABLE skill_packages ADD COLUMN IF NOT EXISTS source_visit_ids JSONB;
