"""
合规检查客户端 — 调 D 的合规审核服务
"""

import os
import logging
from typing import Dict
import httpx

from shared.common.internal_auth import internal_headers

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")


async def check_compliance(content: str, context: dict = None) -> dict:
    """
    调用合规检查服务

    Args:
        content: 待审核的文本
        context: {"user_id": 1, "type": "user_input" | "ai_output"}

    Returns:
        {"blocked": False, "violations": [], "risk_level": "none"}
    """
    context = context or {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{GATEWAY_URL}/api/v1/compliance/check",
                headers=internal_headers(),
                json={"content": content, "context": context}
            )
            resp.raise_for_status()
            return resp.json()["data"]
    except Exception as e:
        logger.error(f"合规检查失败: {e}")
        # 合规服务不可用时的安全策略：放行（避免阻塞业务）
        return {"blocked": False, "violations": [], "risk_level": "none", "error": str(e)}
