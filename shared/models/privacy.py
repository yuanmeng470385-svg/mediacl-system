"""隐私请求（三期 L，需求 3.8(4)(5)/5.7）

医生侧行使查阅/更正/删除/导出/注销权利的请求工单：
  - request_type ∈ view/correct/delete/export/account_delete；
  - status ∈ pending/processing/done/rejected（done/rejected 为终态，不可再处理）；
  - sla_deadline = 创建时间 + 30 自然日（API 层写入；超时仅管理端高亮，不自动执行）；
  - content JSONB：{detail: 申请说明, fields: {full_name, phone}（correct 用）,
    confirm: bool（account_delete 用）, response: 处理回复（handle 写入）}；
  - delete/account_delete 的 done 处理 = users 去标识化（status→deleted + deleted_at），
    物理删除不做（法务拍板）。
"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin

PRIVACY_REQUEST_TYPES = ("view", "correct", "delete", "export", "account_delete")
PRIVACY_REQUEST_STATUSES = ("pending", "processing", "done", "rejected")


class PrivacyRequest(Base, TimestampMixin):
    __tablename__ = "privacy_requests"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    doctor_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    request_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    content = Column(JSONB)
    sla_deadline = Column(DateTime, nullable=False)
    handled_by = Column(BigInteger, ForeignKey("users.id"))
    handled_at = Column(DateTime)
    file_url = Column(String(500))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "doctor_id": self.doctor_id,
            "request_type": self.request_type,
            "status": self.status,
            "content": self.content or {},
            "sla_deadline": self.sla_deadline.isoformat() if self.sla_deadline else None,
            "handled_by": self.handled_by,
            "handled_at": self.handled_at.isoformat() if self.handled_at else None,
            "file_url": self.file_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
