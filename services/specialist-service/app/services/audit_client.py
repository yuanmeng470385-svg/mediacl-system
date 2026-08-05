"""
审计日志客户端 — 调 D 的审计服务
"""

import os
import logging
from typing import Optional, Dict, Any
import httpx

from shared.common.internal_auth import internal_headers

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")


async def write_audit_log(
    service_name: str = "specialist-service",
    user_id: Optional[int] = None,
    action: str = "",
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ai_involved: bool = False,
    ai_model: Optional[str] = None,
    ai_prompt: Optional[str] = None,
    ai_response: Optional[str] = None,
    compliance_result: Optional[Dict] = None,
    request_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    **kwargs
) -> Optional[int]:
    """
    写入审计日志（失败不影响业务）

    Returns:
        日志 ID，失败返回 None
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{GATEWAY_URL}/api/v1/audit/log",
                headers=internal_headers(),
                json={
                    "service_name": service_name,
                    "user_id": user_id,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "ai_involved": ai_involved,
                    "ai_model": ai_model,
                    "ai_prompt": ai_prompt,
                    "ai_response": ai_response,
                    "compliance_result": compliance_result,
                    "request_id": request_id,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                }
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return data.get("id")
    except Exception as e:
        logger.error(f"审计日志写入失败: {e}")
        return None  # 审计失败不影响业务
