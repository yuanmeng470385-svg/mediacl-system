"""审计日志模型"""
from sqlalchemy import Column, String, BigInteger, Boolean, DateTime, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, server_default=func.now())
    service_name = Column(String(50), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(String(100))
    before_value = Column(JSONB)
    after_value = Column(JSONB)
    ai_involved = Column(Boolean, default=False)
    ai_model = Column(String(50))
    ai_prompt_hash = Column(String(100))
    ai_response_hash = Column(String(100))
    compliance_result = Column(JSONB)
    risk_level = Column(String(20))
    client_ip = Column(String(50))
    user_agent = Column(Text)
    request_id = Column(String(100))
