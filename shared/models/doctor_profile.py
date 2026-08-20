"""医生偏好画像模型（需求 5.4 学术偏好引擎 / 附录A doctor_profiles）"""
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class DoctorProfile(Base, TimestampMixin):
    __tablename__ = "doctor_profiles"

    doctor_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    interest_areas = Column(JSONB)
    preferred_doc_type = Column(String(50))
    preferred_style = Column(String(50))
    closed = Column(Boolean, nullable=False, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "doctor_id": self.doctor_id,
            "interest_areas": self.interest_areas,
            "preferred_doc_type": self.preferred_doc_type,
            "preferred_style": self.preferred_style,
            "closed": self.closed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
