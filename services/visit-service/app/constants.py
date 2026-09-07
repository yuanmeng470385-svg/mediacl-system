"""拜访业务常量（visit_manager / visit_record / visit_repo / asr_ws 共用）

独立小模块避免 visit_manager ↔ visit_record 之间的循环导入。
"""

# AI 总结失败时的占位串：记录 ai_summary = 占位串 不等于"已结束"，
# end_visit 可再次调用重试（重试成功覆盖占位串），避免记录永久锁死
AI_SUMMARY_PLACEHOLDER = "（AI 总结生成失败，拜访尚未结束，可重试结束拜访）"

# 合规拦截话术（转写内容预检 / AI 总结审核任一拦截时使用）：记录 ai_summary = 拦截话术
# 视为"已结束"（内容本身有问题，重试无意义，人工复核后另行处理）
AI_SUMMARY_BLOCKED = "该拜访总结因合规问题被拦截，请联系医学顾问复核。"

# visit_records.status 枚举（迁移 008 新增列）：
#   - cancelled 以本列为准（显式取消）；
#   - completed / in_progress 语义仍从 ai_summary 推导（占位串 ≠ 已结束，可重试 end），
#     列值作为回填后的兜底，两处口径必须一致（见 visit_record.to_dict 与 visit_repo.list）
VISIT_STATUS_IN_PROGRESS = "in_progress"
VISIT_STATUS_COMPLETED = "completed"
VISIT_STATUS_CANCELLED = "cancelled"

# 拜访时长上限（分钟，2026-09-07 A-6）：时长=开始到结束的墙钟口径，忘点结束
# 第二天补 end 会记 20h+——按单次拜访常识上限封顶，触顶时 summary 追加异常注记
VISIT_MAX_DURATION_MINUTES = 240
