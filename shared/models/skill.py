"""Skill 模版与审核模型（需求 3.6/附录A skill_packages/skill_audits）"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class SkillPackage(Base, TimestampMixin):
    __tablename__ = "skill_packages"

    name = Column(String(100), nullable=False)
    creator_id = Column(BigInteger, ForeignKey("users.id"))
    is_public = Column(Boolean, nullable=False, default=False)
    is_anonymous = Column(Boolean, nullable=False, default=False)
    audit_status = Column(String(20), default="pending")
    audit_reason = Column(String(500))
    style_tags = Column(JSONB)
    heat = Column(BigInteger, default=0)
    approval_rate = Column(Numeric(5, 4))
    skill_weights = Column(JSONB)   # 任何 API 不返回

    def to_dict(self, expose_weights: bool = False) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "creator_id": self.creator_id,
            "is_public": self.is_public,
            "is_anonymous": self.is_anonymous,
            "audit_status": self.audit_status,
            "audit_reason": self.audit_reason,
            "style_tags": self.style_tags,
            "heat": self.heat,
            "approval_rate": float(self.approval_rate) if self.approval_rate is not None else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if expose_weights:
            d["skill_weights"] = self.skill_weights
        return d


class SkillAudit(Base, TimestampMixin):
    __tablename__ = "skill_audits"

    skill_id = Column(BigInteger, ForeignKey("skill_packages.id"), nullable=False)
    auditor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    audit_result = Column(String(20), nullable=False)
    reason = Column(String(500))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "auditor_id": self.auditor_id,
            "audit_result": self.audit_result,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
