"""数字专员数据模型"""
from sqlalchemy import Column, String, Integer, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base, TimestampMixin


class Specialist(Base, TimestampMixin):
    __tablename__ = "digital_specialists"

    name = Column(String(100), nullable=False)
    product_id = Column(BigInteger, ForeignKey("products.id"))
    persona = Column(JSONB)
    knowledge_scope = Column(JSONB)
    compliance_level = Column(String(20), default="internal")
    bailian_app_id = Column(String(100))
    prompt_version = Column(String(20))
    status = Column(String(20), default="draft")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "product_id": self.product_id,
            "persona": self.persona,
            "compliance_level": self.compliance_level,
            "bailian_app_id": self.bailian_app_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
