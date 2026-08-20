"""患教模板与内容模型（需求 5.5/3.9(2)/附录A）"""
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class PatientEduTemplate(Base, TimestampMixin):
    __tablename__ = "patient_edu_templates"

    title = Column(String(200), nullable=False)
    disease_area = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    version = Column(String(20), default="1.0")
    review_status = Column(String(20), default="pending")
    review_reason = Column(String(500))
    reviewed_by = Column(BigInteger)
    created_by = Column(BigInteger)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "disease_area": self.disease_area,
            "content": self.content,
            "version": self.version,
            "review_status": self.review_status,
            "review_reason": self.review_reason,
            "reviewed_by": self.reviewed_by,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EduContentRecord(Base, TimestampMixin):
    __tablename__ = "edu_content_records"

    doctor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    template_id = Column(BigInteger, ForeignKey("patient_edu_templates.id"))
    content = Column(JSONB, nullable=False)
    is_ai_generated = Column(Boolean, nullable=False, default=True)
    visibility = Column(String(20), default="private")
    audit_status = Column(String(20))   # 三期 M：NULL=未分享；pending/approved/rejected

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "doctor_id": self.doctor_id,
            "template_id": self.template_id,
            "content": self.content,
            "is_ai_generated": self.is_ai_generated,
            "visibility": self.visibility,
            "audit_status": self.audit_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
