-- 024_feedback_unique.sql
-- M-4（2026-08-24 审查修复）：反馈表唯一约束，防评分注水
-- 1) 同一用户对同一对话只允许一条反馈（改主意走 UPDATE，见 conversations.py upsert）
--    —— approval_rate 按 rating==1 聚合，此前可无限重复点赞注水
-- 2) 医生对同一分身的"学术卡片有用"好评只记一条（conversation_id IS NULL 的
--    借表行，见 card_pushes.py）—— useful→useless→useful 反复切换不再重复累加
-- 用法：docker exec -i medagent-postgres psql -U medagent medagent < scripts/migrations/024_feedback_unique.sql

\set ON_ERROR_STOP on

-- 已存在的重复行先收敛（保留每组最新一条），否则唯一索引建不起来
DELETE FROM conversation_feedback a
USING conversation_feedback b
WHERE a.conversation_id IS NOT NULL
  AND a.conversation_id = b.conversation_id
  AND a.user_id = b.user_id
  AND a.id < b.id;

DELETE FROM conversation_feedback a
USING conversation_feedback b
WHERE a.conversation_id IS NULL
  AND a.rating = 1
  AND b.conversation_id IS NULL
  AND b.rating = 1
  AND a.specialist_id = b.specialist_id
  AND a.user_id = b.user_id
  AND a.id < b.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_feedback_user_conversation
    ON conversation_feedback(user_id, conversation_id)
    WHERE conversation_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_feedback_card_useful
    ON conversation_feedback(user_id, specialist_id)
    WHERE conversation_id IS NULL AND rating = 1;
