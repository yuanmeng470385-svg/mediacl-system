"""拜访后续任务模型"""
from sqlalchemy import Column, BigInteger, String, Date, Text, ForeignKey, DateTime, func
from shared.models.base import Base

# 注册外键引用表的元数据（否则 SQLAlchemy 报 NoReferencedTableError）：
# tasks.visit_id → visit_records、tasks.user_id → users
import app.models.visit_record  # noqa: F401
import shared.models.user  # noqa: F401


class Task(Base):
    """任务（映射 tasks 表）

    不继承 TimestampMixin（避免映射表上不存在的列导致真实查询失败），
    列显式定义，与表逐列一致（scripts/init_db.sql + 迁移 003）。
    """
    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    visit_id = Column(BigInteger, ForeignKey("visit_records.id"))
    user_id = Column(BigInteger, ForeignKey("users.id"))
    title = Column(String(500), nullable=False)
    description = Column(Text)
    task_type = Column(String(50), default="follow_up")
    due_date = Column(Date)
    channel = Column(String(50))
    status = Column(String(20), default="open")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "visit_id": self.visit_id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "task_type": self.task_type,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "channel": self.channel,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
