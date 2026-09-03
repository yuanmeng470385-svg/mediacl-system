"""跨服务约定值（非配置，改前缀须两端同步：visit 生成 / specialist 过滤）"""

# visit-service 拜访前准备（prepare_visit）调 specialist chat 的 session_id 前缀。
# prep prompt 是系统指令而非真人提问：specialist-service 的对话检索/使用统计/
# 监控聚合按此前缀排除机器会话，防内部指令污染看板与检索结果。
# NULL 语义：历史上 session_id 可为空的行不属于 prep 会话，过滤条件须放行 NULL。
VISIT_PREP_SESSION_PREFIX = "visit_prep_"


def not_prep_session(column):
    """SQLAlchemy 过滤条件：排除 prep 会话但放行 session_id 为 NULL 的行。

    用法：q.filter(not_prep_session(Conversation.session_id))。
    直接写 ~column.like(...) 会在 NULL 行上得到 NULL（行被误排除）。
    """
    from sqlalchemy import or_
    return or_(column.is_(None), ~column.like(VISIT_PREP_SESSION_PREFIX + "%"))
