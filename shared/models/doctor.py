"""医生端模型（一期 B）：医师认证 / 分身订阅 / 知情同意留痕 / 分享链接"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import declarative_base

from shared.models.base import Base, TimestampMixin


class DoctorCertification(Base, TimestampMixin):
    __tablename__ = "doctor_certifications"
    doctor_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    cert_type = Column(String(20), nullable=False)          # physician / practice（资格证/执业证）
    cert_image_url = Column(String(500), nullable=False)    # OSS URL
    cert_status = Column(String(20), default="pending")     # pending/approved/rejected
    reject_reason = Column(String(500))
    reviewed_by = Column(BigInteger)
    reviewed_at = Column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "doctor_id": self.doctor_id, "cert_type": self.cert_type,
            "cert_image_url": self.cert_image_url, "cert_status": self.cert_status,
            "reject_reason": self.reject_reason, "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class DoctorTwinSubscription(Base, TimestampMixin):
    __tablename__ = "doctor_twin_subscriptions"
    __table_args__ = (UniqueConstraint("doctor_id", "twin_id", name="uq_doctor_twin"),)
    doctor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    twin_id = Column(BigInteger, ForeignKey("digital_specialists.id"), nullable=False)
    status = Column(String(20), default="subscribed")       # subscribed/blocked
    consent_version = Column(String(20), nullable=False)
    consent_at = Column(DateTime, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "doctor_id": self.doctor_id, "twin_id": self.twin_id,
            "status": self.status, "consent_version": self.consent_version,
            "consent_at": self.consent_at.isoformat() if self.consent_at else None,
        }


class DoctorConsent(Base, TimestampMixin):
    __tablename__ = "doctor_consents"
    doctor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    twin_id = Column(BigInteger, ForeignKey("digital_specialists.id"))  # 可空 = 平台级同意
    consent_type = Column(String(20), nullable=False)       # twin / platform
    version = Column(String(20), nullable=False)
    agreed_at = Column(DateTime, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "doctor_id": self.doctor_id, "twin_id": self.twin_id,
            "consent_type": self.consent_type, "version": self.version,
            "agreed_at": self.agreed_at.isoformat() if self.agreed_at else None,
        }


class ShareLink(Base):
    __tablename__ = "share_links"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    twin_id = Column(BigInteger, ForeignKey("digital_specialists.id"), nullable=False)
    url_token = Column(String(64), unique=True, nullable=False)
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    expire_at = Column(DateTime)
    add_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "twin_id": self.twin_id, "url_token": self.url_token,
            "created_by": self.created_by,
            "add_count": self.add_count or 0,
            "expire_at": self.expire_at.isoformat() if self.expire_at else None,
        }
