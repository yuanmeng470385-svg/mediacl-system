"""
审计日志引擎

所有审计日志不可修改、不可删除（数据库层面 REVOKE UPDATE/DELETE）。
记录所有 AI 决策、用户操作、合规检查结果。
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from shared.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class AuditLogger:
    """审计日志记录器 — 异步写入，不影响主业务"""

    def log(
        self,
        db: Session,
        *,
        service_name: str,
        user_id: Optional[int] = None,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        before_value: Any = None,
        after_value: Any = None,
        ai_involved: bool = False,
        ai_model: Optional[str] = None,
        ai_prompt: Optional[str] = None,
        ai_response: Optional[str] = None,
        compliance_result: Optional[Dict] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        写入一条审计日志

        如果 ai_prompt 或 ai_response 传入原文，只存 SHA-256 hash（安全 + 省空间）
        返回日志 ID，失败返回 None（不影响业务）
        """
        try:
            ai_prompt_hash = (
                hashlib.sha256(ai_prompt.encode("utf-8")).hexdigest()
                if ai_prompt else None
            )
            ai_response_hash = (
                hashlib.sha256(ai_response.encode("utf-8")).hexdigest()
                if ai_response else None
            )

            risk_level = None
            if compliance_result:
                risk_level = compliance_result.get("risk_level")

            log_entry = AuditLog(
                timestamp=datetime.now(timezone.utc),
                service_name=service_name,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                before_value=before_value,
                after_value=after_value,
                ai_involved=ai_involved,
                ai_model=ai_model,
                ai_prompt_hash=ai_prompt_hash,
                ai_response_hash=ai_response_hash,
                compliance_result=compliance_result,
                risk_level=risk_level,
                client_ip=client_ip,
                user_agent=user_agent,
                request_id=request_id,
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
            return log_entry.id

        except Exception as e:
            logger.error(f"审计日志写入失败: {e}")
            db.rollback()
            return None  # 审计日志失败不影响业务

    def log_batch(
        self,
        db: Session,
        entries: list,
    ) -> int:
        """批量写入审计日志（用于高频场景），返回成功条数"""
        count = 0
        for entry in entries:
            if self.log(db, **entry):
                count += 1
        return count


# 全局单例
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
