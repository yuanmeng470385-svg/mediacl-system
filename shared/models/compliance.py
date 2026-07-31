"""合规审核模型"""
from sqlalchemy import Column, String, Integer, Boolean, BigInteger, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base, TimestampMixin


class ComplianceRule(Base, TimestampMixin):
    __tablename__ = "compliance_rules"

    rule_code = Column(String(50), unique=True, nullable=False)
    rule_name = Column(String(200), nullable=False)
    rule_type = Column(String(50), nullable=False)   # keyword / regex / semantic
    content = Column(JSONB, nullable=False)
    severity = Column(String(20), default="high")     # high / medium / low
    action = Column(String(20), default="reject")     # reject / warn / log
    description = Column(String)
    enabled = Column(Boolean, default=True)
    version = Column(Integer, default=1)
    created_by = Column(BigInteger, ForeignKey("users.id"))

    def to_dict(self):
        return {
            "id": self.id,
            "rule_code": self.rule_code,
            "rule_name": self.rule_name,
            "rule_type": self.rule_type,
            "content": self.content,
            "severity": self.severity,
            "action": self.action,
            "description": self.description,
            "enabled": self.enabled,
            "version": self.version,
        }


class ComplianceBlock(Base):
    __tablename__ = "compliance_blocks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    service_name = Column(String(50))
    content = Column(String)
    rule_code = Column(String(50))
    rule_name = Column(String(200))
    severity = Column(String(20))
    action = Column(String(20))
    context = Column(JSONB)
    blocked_at = Column(DateTime, server_default=func.now())
