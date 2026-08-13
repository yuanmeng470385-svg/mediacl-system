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


async def check_compliance(content: str, context: dict = None, fast: bool = False,
                           service_name: str = "specialist") -> dict:
    """
    调用合规检查服务

    Args:
        content: 待审核的文本
        context: {"user_id": 1, "type": "user_input" | "ai_output"}
        fast: 快速模式（流式逐帧门禁）—— 只跑关键词/正则，跳语义层，不写拦截记录
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
                json={"content": content, "context": context, "fast": fast,
                      "service_name": service_name}
            )
            resp.raise_for_status()
            return resp.json()["data"]
    except Exception as e:
        # B5 修复（2026-08-12）：合规服务不可用 → 抛异常（fail-closed），绝不静默放行。
        # 调用方（answer_generator 提问预检 / 答案审核 / 流式逐帧门禁）异常传播 →
        # 对话失败 5xx —— 内容在合规不可用时不会被生成/透出。
        logger.error(f"合规检查失败（fail-closed，拒绝处理）: {e}")
        raise
