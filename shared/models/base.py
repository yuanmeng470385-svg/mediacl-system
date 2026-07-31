"""
共享数据模型
- ORM 基类
"""

from datetime import datetime
from sqlalchemy import Column, BigInteger, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TimestampMixin:
    """自动添加 created_at 和 updated_at"""
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
