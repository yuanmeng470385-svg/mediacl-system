"""拜访记录数据模型"""
from datetime import datetime
from sqlalchemy import Column, String, BigInteger, ForeignKey, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base, TimestampMixin

# 注册外键引用表的元数据（否则 SQLAlchemy 报 NoReferencedTableError）：
# visit_records.hcp_id → hcps、product_id → products、specialist_id → digital_specialists
import shared.models.hcp  # noqa: F401
import shared.models.product  # noqa: F401
import shared.models.digital_specialist  # noqa: F401


class VisitRecord(Base, TimestampMixin):
    """拜访记录（映射 visit_records 表）

    表无 status 字段，业务状态以 ai_summary 是否生成为准：
      in_progress — ai_summary IS NULL（已开始未结束）
      completed   — ai_summary 非空（已生成结构化总结）
    """
    __tablename__ = "visit_records"

    hcp_id = Column(BigInteger, ForeignKey("hcps.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    product_id = Column(BigInteger, ForeignKey("products.id"))
    specialist_id = Column(BigInteger, ForeignKey("digital_specialists.id"))
    visit_time = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer)
    conversation_transcript = Column(String)          # 转写全文（分段追加）
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
        status = "completed" if self.ai_summary else "in_progress"
        return {
            "id": self.id,
            "hcp_id": self.hcp_id,
            "user_id": self.user_id,
            "product_id": self.product_id,
            "specialist_id": self.specialist_id,
            "visit_time": self.visit_time.isoformat() if self.visit_time else None,
            "duration_minutes": self.duration_minutes,
            "status": status,  # 派生状态：无 ai_summary 视为进行中
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
