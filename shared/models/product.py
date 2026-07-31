"""产品模型"""
from sqlalchemy import Column, String, Date, Text
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    product_code = Column(String(50), unique=True, nullable=False)
    product_name = Column(String(200), nullable=False)
    generic_name = Column(String(200))
    manufacturer = Column(String(200))
    indication = Column(Text)
    approval_date = Column(Date)
    status = Column(String(20), default="active")
    extra = Column("metadata", JSONB)  # 列名仍为 metadata，属性名避免保留字冲突
