"""合规检查客户端 — 调 D 的合规审核服务（实时转写/拜访总结审核）"""
import os
import logging
from typing import Dict
import httpx

from shared.common.internal_auth import internal_headers

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")


async def check_compliance(content: str, context: dict = None,
                           service_name: str = "visit") -> dict:
    """
    调用合规检查服务

    Args:
        content: 待审核的文本
        context: {"user_id": 1, "type": "user_input" | "ai_output"}
        service_name: 调用方服务名（2026-08-11：显式传参，拦截记录/监管报告
            "按服务"统计不再混入内容类型 user_input/ai_output）

    Returns:
        {"blocked": False, "violations": [], "risk_level": "none"}
    """
    context = context or {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{GATEWAY_URL}/api/v1/compliance/check",
                headers=internal_headers(),
                json={"content": content, "context": context, "service_name": service_name}
            )
            resp.raise_for_status()
            return resp.json()["data"]
    except Exception as e:
        logger.error(f"合规检查失败: {e}")
        # 合规服务不可用时的安全策略：放行（避免阻塞业务）
        return {"blocked": False, "violations": [], "risk_level": "none", "error": str(e)}
