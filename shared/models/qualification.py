"""代表备案与资质模型（需求文档 3.3/4.2/附录A representative_qualifications）"""
from datetime import date

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, String

from shared.models.base import Base, TimestampMixin


class RepresentativeQualification(Base, TimestampMixin):
    __tablename__ = "representative_qualifications"

    representative_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    education_cert = Column(String(500), nullable=False)   # OSS URL（学历证明）
    training_cert = Column(String(500))                    # OSS URL（培训合格证明，可空）
    audit_status = Column(String(20), default="pending")   # pending/approved/rejected
    filing_number = Column(String(50))                     # 国家备案平台备案号
    filing_expire_date = Column(Date)                      # 备案有效期（审核人核对凭证确认）
    reject_reason = Column(String(500))
    reviewed_by = Column(BigInteger)
    reviewed_at = Column(DateTime)
    # 二期培训考试字段（本计划只建列，不接线 UI/接口）
    compliance_training_completed = Column(Boolean, default=False)
    compliance_exam_score = Column(Integer)
    commitment_signed = Column(Boolean, default=False)

    def _filing_status(self) -> str:
        """派生状态：未备案 > 已过期 > 有效。不落库，避免与日期列双写不一致。"""
        if not (self.filing_number or "").strip():
            return "not_filed"
        if self.filing_expire_date and self.filing_expire_date < date.today():
            return "expired"
        return "valid"

    def to_dict(self) -> dict:
        expire = self.filing_expire_date
        return {
            "id": self.id,
            "representative_id": self.representative_id,
            "education_cert": self.education_cert,
            "training_cert": self.training_cert,
            "audit_status": self.audit_status,
            "filing_number": self.filing_number,
            "filing_status": self._filing_status(),
            "filing_expire_date": expire.isoformat() if expire else None,
            "days_until_expiry": (expire - date.today()).days if expire else None,
            "reject_reason": self.reject_reason,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "compliance_training_completed": self.compliance_training_completed,
            "compliance_exam_score": self.compliance_exam_score,
            "commitment_signed": self.commitment_signed,
        }
