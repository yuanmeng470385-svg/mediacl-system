"""知识检索反馈模型

注意：knowledge_feedback 表（迁移 003）只有 created_at，无 updated_at 列，
故不继承 TimestampMixin（其会映射 updated_at），字段定义与表结构保持一致。
"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, SmallInteger, String, Text, func

from shared.models.base import Base


class KnowledgeFeedback(Base):
    __tablename__ = "knowledge_feedback"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    query = Column(Text, nullable=False)
    doc_id = Column(String(100))
    rating = Column(SmallInteger, nullable=False)  # 1 有用 / -1 无用
    comment = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
