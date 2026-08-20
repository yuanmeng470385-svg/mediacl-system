"""Skill 模版与审核模型（需求 3.6/附录A skill_packages/skill_audits；三期 J 下架）"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Numeric, String, Text
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
    skill_weights = Column(JSONB)          # 任何 API 不返回
    # 三期 J：代表发布内容字段
    description = Column(String(200))      # 治疗领域/一句话说明（元数据，公共列表展示）
    content = Column(Text)                 # 话术素材（内容，仅审核人受控查看）
    # 三期 J：下架（3.6(3)）
    off_shelf_status = Column(String(20), nullable=False, default="active")  # active/off_shelved
    off_shelf_reason = Column(String(500))
    off_shelf_type = Column(String(20))    # compliance/author
    off_shelf_by = Column(BigInteger, ForeignKey("users.id"))
    off_shelf_at = Column(DateTime)

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
            "description": self.description,
            "off_shelf_status": self.off_shelf_status,
            "off_shelf_reason": self.off_shelf_reason,
            "off_shelf_type": self.off_shelf_type,
            "off_shelf_by": self.off_shelf_by,
            "off_shelf_at": self.off_shelf_at.isoformat() if self.off_shelf_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if expose_weights:
            d["skill_weights"] = self.skill_weights
            d["content"] = self.content
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


class SkillOffShelf(Base, TimestampMixin):
    """下架记录存档（3.6(3) 下架操作记录存档）"""
    __tablename__ = "skill_off_shelves"

    skill_id = Column(BigInteger, ForeignKey("skill_packages.id"), nullable=False)
    operator_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    off_shelf_type = Column(String(20), nullable=False)
    reason = Column(String(500))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "operator_id": self.operator_id,
            "off_shelf_type": self.off_shelf_type,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
