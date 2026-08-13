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

# A6 审计防静默丢：字符串列长度上限（与 shared/models/audit_log.py 及
# scripts/init_db.sql 对齐）。调用方（各业务服务）塞超长值时按列长截断，
# 保证至少落一条截断记录——否则整条 INSERT 因 DataError 失败、被
# log() 的 except 吞掉后审计留痕静默丢失。user_agent 是 TEXT 列不截断。
_COLUMN_MAX_LEN = {
    "service_name": 50,
    "action": 100,
    "resource_type": 50,
    "resource_id": 100,
    "ai_model": 50,
    "ai_prompt_hash": 100,
    "ai_response_hash": 100,
    "risk_level": 20,
    "client_ip": 50,
    "request_id": 100,
}


def _truncate(value, max_len: int):
    """字符串按列长截断；非字符串原样返回。"""
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len]
    return value


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
        **kwargs,
    ) -> Optional[int]:
        """
        写入一条审计日志

        如果 ai_prompt 或 ai_response 传入原文，只存 SHA-256 hash（安全 + 省空间）
        返回日志 ID，失败返回 None（不影响业务）

        注意：**kwargs 吸收调用方多传的未知键（如 payload 里的业务扩展字段），
        否则 `log(db, **request)` 会在函数体外抛 TypeError 导致 500 且日志静默丢失。
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
                service_name=_truncate(service_name, _COLUMN_MAX_LEN["service_name"]),
                user_id=user_id,
                action=_truncate(action, _COLUMN_MAX_LEN["action"]),
                resource_type=_truncate(resource_type, _COLUMN_MAX_LEN["resource_type"]),
                resource_id=_truncate(resource_id, _COLUMN_MAX_LEN["resource_id"]),
                before_value=before_value,
                after_value=after_value,
                ai_involved=ai_involved,
                ai_model=_truncate(ai_model, _COLUMN_MAX_LEN["ai_model"]),
                ai_prompt_hash=_truncate(ai_prompt_hash, _COLUMN_MAX_LEN["ai_prompt_hash"]),
                ai_response_hash=_truncate(ai_response_hash, _COLUMN_MAX_LEN["ai_response_hash"]),
                compliance_result=compliance_result,
                risk_level=_truncate(risk_level, _COLUMN_MAX_LEN["risk_level"]),
                client_ip=_truncate(client_ip, _COLUMN_MAX_LEN["client_ip"]),
                user_agent=user_agent,
                request_id=_truncate(request_id, _COLUMN_MAX_LEN["request_id"]),
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
