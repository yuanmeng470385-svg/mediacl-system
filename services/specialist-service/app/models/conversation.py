"""对话记录模型"""
from sqlalchemy import Column, String, Integer, BigInteger, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    specialist_id = Column(BigInteger, ForeignKey("digital_specialists.id"))
    session_id = Column(String(100))
    role = Column(String(20), nullable=False)     # user / assistant
    content = Column(Text, nullable=False)
    citations = Column(JSONB)
    compliance_result = Column(JSONB)
    tokens_used = Column(Integer)
    latency_ms = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "specialist_id": self.specialist_id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "citations": self.citations,
            "compliance_result": self.compliance_result,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
