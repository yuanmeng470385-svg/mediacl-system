"""学术触达模型（需求 4.6/5.3/6.3/附录A push_records + 站内通知）"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class AcademicCard(Base, TimestampMixin):
    __tablename__ = "academic_cards"

    representative_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(JSONB, nullable=False)
    is_ai_generated = Column(Boolean, nullable=False, default=True)
    compliance_status = Column(String(20), default="passed")
    status = Column(String(20), default="active")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "representative_id": self.representative_id,
            "title": self.title,
            "content": self.content,
            "is_ai_generated": self.is_ai_generated,
            "compliance_status": self.compliance_status,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CardPushRecord(Base, TimestampMixin):
    __tablename__ = "card_push_records"
    __table_args__ = (UniqueConstraint("card_id", "doctor_id", name="uq_push"),)

    representative_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    card_id = Column(BigInteger, ForeignKey("academic_cards.id"), nullable=False)
    doctor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    read_status = Column(String(20), default="unread")
    read_at = Column(DateTime)
    tracked_seconds = Column(Integer, default=0)
    feedback = Column(String(500))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "representative_id": self.representative_id,
            "card_id": self.card_id,
            "doctor_id": self.doctor_id,
            "read_status": self.read_status,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "tracked_seconds": self.tracked_seconds,
            "feedback": self.feedback,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    type = Column(String(20), nullable=False)   # briefing_ready / card_feedback / card_question
    title = Column(String(200), nullable=False)
    content = Column(String(1000))
    link = Column(String(200))
    is_read = Column(Boolean, nullable=False, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "content": self.content,
            "link": self.link,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
