"""陪练会话模型（需求 4.5 自动评分与进步曲线）"""
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class PracticeSession(Base, TimestampMixin):
    __tablename__ = "practice_sessions"

    representative_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    skill_id = Column(BigInteger, ForeignKey("skill_packages.id"))
    scenario = Column(String(100))
    status = Column(String(20), default="in_progress")
    scores = Column(JSONB)
    turn_count = Column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "representative_id": self.representative_id,
            "skill_id": self.skill_id,
            "scenario": self.scenario,
            "status": self.status,
            "scores": self.scores,
            "turn_count": self.turn_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
