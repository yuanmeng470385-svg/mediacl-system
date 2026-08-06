"""审计日志客户端 — 登录/发码行为留痕（失败不影响业务）"""

import os
import logging
from typing import Optional, Dict

import httpx

from shared.common.internal_auth import internal_headers

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")


async def write_audit_log(
    action: str,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    before_value: Optional[Dict] = None,
    after_value: Optional[Dict] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Optional[int]:
    """写入审计日志。审计不可用不应阻断登录，故失败仅记日志。"""
    payload = {
        "service_name": "auth-service",
        "user_id": user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "client_ip": client_ip,
        "user_agent": user_agent,
        "request_id": request_id,
    }
    # before_value/after_value 可选透传（变更快照留痕）：为 None 时不携带，
    # 参照 specialist/hcp 服务的透传模式
    if before_value is not None:
        payload["before_value"] = before_value
    if after_value is not None:
        payload["after_value"] = after_value
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{GATEWAY_URL}/api/v1/audit/log",
                headers=internal_headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json().get("data", {}).get("id")
    except Exception as exc:
        logger.error(f"审计日志写入失败: {exc}")
        return None
