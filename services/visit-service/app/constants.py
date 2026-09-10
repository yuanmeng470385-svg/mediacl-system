"""拜访业务常量（visit_manager / visit_record / visit_repo / asr_ws 共用）

独立小模块避免 visit_manager ↔ visit_record 之间的循环导入。

2026-09-10 起 AI_SUMMARY_PLACEHOLDER 与三个状态枚举的本体在
shared/models/visit.py（VisitRecord 提升到 shared 时随迁，单一事实源），
此处 re-export 保持本服务各处 `from app.constants import ...` 不变。
"""

from shared.models.visit import (  # noqa: F401 -- re-export，勿在本文件重定义
    AI_SUMMARY_PLACEHOLDER,
    VISIT_STATUS_IN_PROGRESS,
    VISIT_STATUS_COMPLETED,
    VISIT_STATUS_CANCELLED,
)

# 合规拦截话术（转写内容预检 / AI 总结审核任一拦截时使用）：记录 ai_summary = 拦截话术
# 视为"已结束"（内容本身有问题，重试无意义，人工复核后另行处理）
AI_SUMMARY_BLOCKED = "该拜访总结因合规问题被拦截，请联系医学顾问复核。"

# 拜访时长上限（分钟，2026-09-07 A-6）：时长=开始到结束的墙钟口径，忘点结束
# 第二天补 end 会记 20h+——按单次拜访常识上限封顶，触顶时 summary 追加异常注记
VISIT_MAX_DURATION_MINUTES = 240
