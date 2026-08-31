"""
审计日志客户端 — 调 D 的审计服务
"""

import os
import logging
from typing import Optional, Dict, Any
import httpx

from shared.common.internal_auth import internal_headers
from shared.common.context import get_request_id

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")


async def write_audit_log(
    service_name: str = "specialist-service",
    user_id: Optional[int] = None,
    action: str = "",
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    before_value: Any = None,
    after_value: Any = None,
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
    # 链路追踪（需求 7.1）：调用方未显式传 request_id 时从 context 取
    # （RequestIDMiddleware 已写入），审计记录可关联到全链路 ID
    if request_id is None:
        request_id = get_request_id() or None
    payload = {
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
    # before_value/after_value 可选透传（专员 CRUD 变更快照留痕）：为 None 时不携带，
    # 保持既有 payload 形态（参照 hcp-service 的透传模式）
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
            data = resp.json().get("data", {})
            return data.get("id")
    except Exception as e:
        logger.error(f"审计日志写入失败: {e}")
        return None  # 审计失败不影响业务


async def count_audit_logs(
    action: str,
    user_id: Optional[int] = None,
    since: Optional[str] = None,
) -> Optional[int]:
    """
    按条件计数审计日志（三期 P 决策 4：每日提取限额的数据源）

    Args:
        action: 操作类型（如 "skill_extract_draft"）
        user_id: 用户 ID
        since: 起始时间 ISO 格式（UTC）

    Returns:
        命中条数，查询失败返回 None（调用方放行——审计可用性不卡死业务，
        与 write_audit_log 失败不阻断同语义）
    """
    params = {"action": action}
    if user_id is not None:
        params["user_id"] = user_id
    if since:
        params["since"] = since
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{GATEWAY_URL}/api/v1/audit/count",
                headers=internal_headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            total = data.get("total")
            return total if isinstance(total, int) else None
    except Exception as e:
        logger.warning(f"审计日志计数查询失败（限额放行）: {e}")
        return None
