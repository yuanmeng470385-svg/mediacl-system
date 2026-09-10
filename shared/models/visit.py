"""拜访记录数据模型（共享）

visit-service 与 specialist-service 共用：分身从历史记录生成风格
（specialists.py style-from-records）需要读拜访转写中代表本人的发言，
照 digital_specialist 的 shared 模式提升本体，visit-service 侧
app/models/visit_record.py 改为 re-export。

模型依赖的三个常量（占位串/状态枚举）随模型一同提升为单一事实源，
visit-service/app/constants.py 从此处 re-export。
"""
from datetime import datetime
from sqlalchemy import Column, String, BigInteger, ForeignKey, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base, TimestampMixin

# AI 总结失败时的占位串：记录 ai_summary = 占位串 不等于"已结束"，
# end_visit 可再次调用重试（重试成功覆盖占位串），避免记录永久锁死
AI_SUMMARY_PLACEHOLDER = "（AI 总结生成失败，拜访尚未结束，可重试结束拜访）"

# visit_records.status 枚举（迁移 008 新增列）：
#   - cancelled 以本列为准（显式取消）；
#   - completed / in_progress 语义仍从 ai_summary 推导（占位串 ≠ 已结束，可重试 end），
#     列值作为回填后的兜底，两处口径必须一致（见 visit_record.to_dict 与 visit_repo.list）
VISIT_STATUS_IN_PROGRESS = "in_progress"
VISIT_STATUS_COMPLETED = "completed"
VISIT_STATUS_CANCELLED = "cancelled"

# 拜访转写行首说话人前缀（visit_manager 追加转写时落库，2026-08-27 双方分离）：
# 代表本人的发言行以 "[代表] " 开头，跨服务读取素材按此前缀过滤
VISIT_TRANSCRIPT_REP_PREFIX = "[代表] "
VISIT_TRANSCRIPT_DOCTOR_PREFIX = "[医生] "

# 注册外键引用表的元数据（否则 SQLAlchemy 报 NoReferencedTableError）：
# visit_records.hcp_id → hcps、product_id → products、specialist_id → digital_specialists
import shared.models.hcp  # noqa: F401
import shared.models.product  # noqa: F401
import shared.models.digital_specialist  # noqa: F401


class VisitRecord(Base, TimestampMixin):
    """拜访记录（映射 visit_records 表）

    业务状态推导口径（与 visit_repo.list 一致，见 to_dict）：
      in_progress — ai_summary IS NULL 或等于占位串（AI 失败可重试 end）
      completed   — ai_summary 非空且非占位串（含合规拦截话术）
      cancelled   — 以 status 列为准（迁移 008 新增）
    """

    __tablename__ = "visit_records"

    hcp_id = Column(BigInteger, ForeignKey("hcps.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    product_id = Column(BigInteger, ForeignKey("products.id"))
    specialist_id = Column(BigInteger, ForeignKey("digital_specialists.id"))
    visit_time = Column(DateTime, nullable=False)
    # 显式状态（迁移 008）。仅 cancelled 以本列为准；completed/in_progress 从
    # ai_summary 推导（历史数据回填见迁移脚本，此处推导对未回填行同样正确）
    status = Column(String(20), nullable=False, default=VISIT_STATUS_IN_PROGRESS)
    duration_minutes = Column(Integer)
    conversation_transcript = Column(String)          # 转写全文（分段追加，行首 [代表]/[医生] 前缀）
    ai_summary = Column(String)                       # AI 结构化总结
    key_points = Column(JSONB)                        # 关键点
    hcp_interests = Column(JSONB)                     # 医生兴趣点
    hcp_objections = Column(JSONB)                    # 医生异议
    follow_up_suggestions = Column(JSONB)             # 跟进建议
    sentiment = Column(String(20))                    # positive / neutral / negative
    compliance_flags = Column(JSONB)                  # 合规检查结果（违规记录）
    next_visit_plan = Column(JSONB)                   # 下次拜访计划
    attachments = Column(JSONB)                       # 附件
    key_nodes = Column(JSONB)                         # LLM 实时推荐：关键节点标记数组

    def to_dict(self):
        # B14：占位串不算"已结束"（可重试 end）；合规拦截话术算已结束；取消以列为准
        if self.status == VISIT_STATUS_CANCELLED:
            status = VISIT_STATUS_CANCELLED
        elif self.ai_summary and self.ai_summary != AI_SUMMARY_PLACEHOLDER:
            status = "completed"
        else:
            status = "in_progress"
        return {
            "id": self.id,
            "hcp_id": self.hcp_id,
            "user_id": self.user_id,
            "product_id": self.product_id,
            "specialist_id": self.specialist_id,
            "visit_time": self.visit_time.isoformat() if self.visit_time else None,
            "duration_minutes": self.duration_minutes,
            "status": status,  # 派生状态：占位串 → in_progress，cancelled → cancelled
            "conversation_transcript": self.conversation_transcript,
            "ai_summary": self.ai_summary,
            "key_points": self.key_points,
            "hcp_interests": self.hcp_interests,
            "hcp_objections": self.hcp_objections,
            "follow_up_suggestions": self.follow_up_suggestions,
            "sentiment": self.sentiment,
            "compliance_flags": self.compliance_flags,
            "next_visit_plan": self.next_visit_plan,
            "attachments": self.attachments,
            "key_nodes": self.key_nodes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
