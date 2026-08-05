"""数字专员客户端 — 调 A 的 chat 接口（生成准备包/拜访总结/跟进建议）"""
import os
import logging
from typing import Optional, Dict
import httpx

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")


async def chat_with_specialist(
    specialist_id: int,
    question: str,
    user_id: int,
    session_id: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Dict:
    """
    调 A 的数字专员对话接口

    Args:
        specialist_id: 数字专员 ID
        question: 给专员的指令（准备包/总结等）
        user_id: 当前用户
        auth_token: 当前用户的 JWT（原样透传）—— chat 接口在网关要求 JWT，
                    不带 token 会 401 → 此前陪访 AI 功能全部永久 degraded

    Returns:
        {"answer": "...", "blocked": false, "session_id": "...", ...}
        失败时返回 {"answer": "", "blocked": false, "error": str(e)}
    """
    try:
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{GATEWAY_URL}/api/v1/specialists/{specialist_id}/chat",
                json={"question": question, "session_id": session_id},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            if not data.get("answer"):
                raise ValueError(f"专员未返回内容: {resp.text[:200]}")
            return data
    except Exception as e:
        logger.error(f"调数字专员失败 (specialist_id={specialist_id}): {e}")
        return {"answer": "", "blocked": False, "error": str(e)}
