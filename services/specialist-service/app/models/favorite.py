"""对话收藏模型

注意：conversation_favorites 表（init_db.sql / 迁移 003）只有 created_at，
无 updated_at 列，故不继承 TimestampMixin（其会映射 updated_at），
字段定义与表结构保持一致。
"""
from sqlalchemy import Column, BigInteger, Text, ForeignKey, UniqueConstraint, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base
import shared.models.digital_specialist  # noqa: F401 注册 FK 元数据


class ConversationFavorite(Base):
    __tablename__ = "conversation_favorites"
    __table_args__ = (UniqueConstraint("user_id", "conversation_id"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(BigInteger, ForeignKey("conversations.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    specialist_id = Column(BigInteger, ForeignKey("digital_specialists.id"))
    question = Column(Text)
    answer = Column(Text)
    citations = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
