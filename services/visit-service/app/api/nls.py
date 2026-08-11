"""NLS 语音能力端点（移动端 TTS 合成用）

移动端拿 {token, appkey} 后直调 NLS REST 合成
（https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts）。
appkey 是项目标识非机密，token 是 AK/SK 换发的短期凭证（24h），
AK/SK 永不离开服务端。
"""
import logging
import os

from fastapi import APIRouter, Depends

from shared.common.auth import require_roles
from shared.common.response import success, BusinessError
from app.services.realtime_asr import get_nls_token, nls_token_expire_at

router = APIRouter(prefix="/api/v1/nls", tags=["nls"])
logger = logging.getLogger(__name__)


@router.get("/tts-token")
async def get_tts_token(
    current_user: dict = Depends(require_roles("rep", "admin", "manager")),
):
    """下发 NLS TTS 合成所需的临时 token + appkey"""
    app_key = os.getenv("NLS_APPKEY", "").strip()
    if not app_key:
        raise BusinessError("NLS 语音合成未配置（缺 NLS_APPKEY）")
    try:
        token = await get_nls_token()
    except Exception as e:
        logger.warning("NLS token 换取失败: %s", e)
        raise BusinessError("NLS token 换取失败，请检查 AK/SK 配置")
    return success({
        "token": token,
        "appkey": app_key,
        "expires_at": nls_token_expire_at(),
    })
