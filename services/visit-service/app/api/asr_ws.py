"""实时转写 WebSocket 端点（移动端录音推流 → NLS 流式识别 → 增量回推）

    WS  /ws/visits/{visit_id}/asr?token=<JWT>

移动端连上后：
  1. 以 Binary Frame 推送 PCM 音频（16k/16bit/单声道）
  2. 服务端转发 NLS 实时语音识别，逐句回推 JSON：
       {"type": "sentence", "index": 1, "text": "..."}          # 中间结果（边说边出字）
       {"type": "sentence", "index": 1, "text": "...", "final": true}   # 断句完成
       {"type": "compliance", "blocked": true, "violations": [...]}     # 该句合规拦截
  3. 发送 {"type": "stop"} 结束转写

鉴权：token 走 query 参数（WebSocket 握手无法带 Authorization 头）；
归属校验沿用 S4 规则（仅本人或 admin）。
fail-closed：NLS_APPKEY 未配置且未显式 NLS_MOCK=1 时拒绝转写（不降级 Mock 污染证据库）；
显式 NLS_MOCK=1 时允许 Mock 联调，但 Mock 文本不落库。
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.exceptions import HTTPException
from websockets.exceptions import ConcurrencyError, ConnectionClosed

from shared.common.auth import verify_token
from shared.common.db_session import SessionLocal

from app.db.repositories.visit_repo import VisitRepo
from app.services.compliance_client import check_compliance
from app.services.realtime_asr import MockRealtimeAsrClient, RealtimeAsrClient

router = APIRouter(tags=["asr"])
logger = logging.getLogger(__name__)


def _get_asr_client():
    """NLS_APPKEY 已配置 → 真实客户端；否则抛错（fail-closed，不降级 Mock 污染证据库）。

    显式开发模式：NLS_MOCK=1 时允许 Mock（文本不落库，见 ws 处理器）。
    """
    import os
    app_key = os.getenv("NLS_APPKEY", "")
    if app_key:
        return RealtimeAsrClient(app_key=app_key), False
    if os.getenv("NLS_MOCK") == "1":
        logger.error("NLS_MOCK=1 显式启用 Mock 实时转写（仅开发联调，文本不落库）")
        return MockRealtimeAsrClient(), True
    raise RuntimeError("实时转写未配置：缺少 NLS_APPKEY（NLS 管控台项目 Appkey）。拒绝降级 Mock，防止假转写污染拜访证据。")


@router.websocket("/ws/visits/{visit_id}/asr")
async def ws_visit_asr(websocket: WebSocket, visit_id: int):
    # ---- 鉴权：query 带 JWT ----
    token = websocket.query_params.get("token", "")
    try:
        payload = verify_token(token)
    except HTTPException:
        await websocket.close(code=4401)  # 未认证
        return
    user_id = int(payload["sub"])
    role = payload.get("role", "")

    # ---- 归属校验（S4）：仅本人或 admin ----
    db = SessionLocal()
    try:
        record = VisitRepo.get(db, visit_id)
        if not record:
            await websocket.close(code=4404)  # 拜访不存在
            return
        if record.user_id != user_id and role != "admin":
            await websocket.close(code=4403)  # 无权
            return

        await websocket.accept()
        # 串行化该连接的所有 send：后台合规任务与主路径并发 send 会触发
        # websockets>=12 的 ConcurrencyError（事件被吞、合规拦截丢失）
        send_lock = asyncio.Lock()
        async with send_lock:
            await websocket.send_json({"type": "ready", "visit_id": visit_id})

        try:
            asr, is_mock = _get_asr_client()
        except RuntimeError as exc:
            async with send_lock:
                await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=4500)  # 服务端未配置
            return

        async def on_sentence(text: str, index: int, is_final: bool):
            # 回推增量/断句给 App
            async with send_lock:
                await websocket.send_json({
                    "type": "sentence", "index": index, "text": text, "final": is_final,
                })
            # 断句完成：追加到拜访记录 + 实时合规检查
            if is_final:
                # fail-closed：Mock 会话的文本绝不落库（防止假转写污染证据库）
                if is_mock:
                    logger.warning("Mock 转写文本不落库: %s", text[:50])
                else:
                    rec = VisitRepo.get(db, visit_id)
                    if rec:
                        rec.conversation_transcript = (rec.conversation_transcript or "") + text + "\n"
                        db.commit()
                async def _check_later():
                    try:
                        compliance = await check_compliance(
                            text,
                            {"user_id": user_id, "type": "live_conversation", "visit_id": visit_id},
                        )
                        if compliance.get("blocked"):
                            async with send_lock:
                                await websocket.send_json({
                                    "type": "compliance",
                                    "blocked": True,
                                    "violations": compliance.get("violations", []),
                                })
                    except (ConcurrencyError, ConnectionClosed):
                        # 客户端已断开或发送竞争：跳过推送，不是合规检查失败
                        logger.info("客户端已断开或发送竞争，跳过合规推送")
                    except Exception as exc:
                        logger.error("实时合规检查失败: %s", exc)
                asyncio.create_task(_check_later())  # 不阻塞转写流（<2s 承诺）

        await asr.start(on_sentence=on_sentence)

        try:
            while True:
                frame = await websocket.receive()
                if frame.get("type") == "websocket.disconnect":
                    break
                data = frame.get("bytes") or frame.get("text")
                if not data:
                    continue
                if isinstance(data, str):
                    # 控制帧 {"type":"stop"} → 结束转写
                    try:
                        ctrl = json.loads(data)
                    except json.JSONDecodeError:
                        ctrl = {}
                    if ctrl.get("type") == "stop":
                        await asr.finish()
                        break
                    continue
                # 二进制 = PCM 音频分片 → 转发 NLS
                await asr.feed(data)
        except WebSocketDisconnect:
            logger.info(f"客户端断开: visit_id={visit_id}")
        finally:
            await asr.close()
            try:
                async with send_lock:
                    await websocket.send_json({"type": "completed"})
            except Exception:
                pass  # 客户端已断开
    finally:
        db.close()
