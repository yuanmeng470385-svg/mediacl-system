"""分身夜间简报模型（一期 C）：每日聚合 doctor 对话生成的简报"""
from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base


class NightlyBriefing(Base):
    __tablename__ = "nightly_briefings"
    __table_args__ = (UniqueConstraint("representative_id", "specialist_id", "briefing_date",
                                       name="uq_nb_rep_spec_date"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    representative_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    specialist_id = Column(BigInteger, ForeignKey("digital_specialists.id"), nullable=False)
    briefing_date = Column(Date, nullable=False)          # 简报日（聚合前一天对话）
    content = Column(JSONB, nullable=False)               # {summary, doctors:[{doctor_name,questions,concern,follow_up}]}
    status = Column(String(20), default="ready")          # ready/generating/failed
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "representative_id": self.representative_id,
            "specialist_id": self.specialist_id,
            "briefing_date": self.briefing_date.isoformat() if self.briefing_date else None,
            "content": self.content, "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
