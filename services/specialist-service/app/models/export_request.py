"""数据导出审批记录模型（三期 K，需求 3.8(3)）"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String

from shared.models.base import Base, TimestampMixin


class ExportRequest(Base, TimestampMixin):
    __tablename__ = "export_requests"

    requester_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    export_type = Column(String(50), nullable=False, default="conversations")
    reason = Column(String(500))
    status = Column(String(20), nullable=False, default="pending")  # pending/approved/rejected
    approver_id = Column(BigInteger, ForeignKey("users.id"))
    approve_reason = Column(String(500))
    file_url = Column(String(500))
    expires_at = Column(DateTime)
    responded_at = Column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "requester_id": self.requester_id,
            "export_type": self.export_type,
            "reason": self.reason,
            "status": self.status,
            "approver_id": self.approver_id,
            "approve_reason": self.approve_reason,
            "file_url": self.file_url,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
