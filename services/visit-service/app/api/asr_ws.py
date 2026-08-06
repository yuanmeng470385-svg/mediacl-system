"""实时转写 WebSocket 端点（移动端录音推流 → NLS 流式识别 → 增量回推）

    WS  /ws/visits/{visit_id}/asr?token=<JWT>

移动端连上后：
  1. 以 Binary Frame 推送 PCM 音频（16k/16bit/单声道）
  2. 服务端转发 NLS 实时语音识别，逐句回推 JSON（speaker 字段：双方分离，
     有真实说话人信息时映射为 "rep"/"doctor"，无信息缺省 "rep"）：
       {"type": "sentence", "index": 1, "text": "...", "speaker": "rep"}          # 中间结果
       {"type": "sentence", "index": 1, "text": "...", "final": true, "speaker": "rep"}   # 断句完成
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


def _map_speaker(speaker) -> str:
    """NLS 说话人信息 → 回推帧 speaker 字段（"rep"/"doctor"）

    已归一化的 "rep"/"doctor" 直接透传（Mock 路径）；
    NLS 数字 speaker_id 按 0=代表(rep) / 1=医生(doctor) 映射（双方分离约定，待真机确认）；
    无信息 / 未知取值缺省 "rep"（移动端已约定缺省 rep）。
    """
    if speaker in ("rep", "doctor"):
        return speaker
    if speaker in (0, "0"):
        return "rep"
    if speaker in (1, "1"):
        return "doctor"
    return "rep"


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

        # 断句完成落库的最后一句缓冲：on_sentence 与会话收尾存在 db 关闭竞态，
        # 落库失败会静默丢失 → 缓冲该句，会话收尾（finally）兜底落库
        last_final_text = None

        async def on_sentence(text: str, index: int, is_final: bool, speaker=None):
            nonlocal last_final_text
            # 回推增量/断句给 App（统一携带 speaker 字段：双方分离，缺省 rep）
            async with send_lock:
                await websocket.send_json({
                    "type": "sentence", "index": index, "text": text, "final": is_final,
                    "speaker": _map_speaker(speaker),
                })
            # 断句完成：追加到拜访记录 + 实时合规检查
            if is_final:
                # fail-closed：Mock 会话的文本绝不落库（防止假转写污染证据库）
                if is_mock:
                    logger.warning("Mock 转写文本不落库: %s", text[:50])
                else:
                    try:
                        rec = VisitRepo.get(db, visit_id)
                        if rec:
                            rec.conversation_transcript = (rec.conversation_transcript or "") + text + "\n"
                            db.commit()
                        last_final_text = None  # 落库成功，清空缓冲
                    except Exception as exc:
                        # 落库失败（如 db 已关闭的竞态）→ 缓冲该句，会话收尾兜底
                        logger.error("断句落库失败，留待会话收尾兜底: visit_id=%s err=%s", visit_id, exc)
                        last_final_text = text
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
                    except (ConcurrencyError, ConnectionClosed, RuntimeError):
                        # 客户端已断开 / 发送竞争 / 连接关闭后 starlette send 抛 RuntimeError：
                        # 跳过推送，不是合规检查失败
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
            # 收尾兜底落库：on_sentence 缓冲的最后一句；会话已关闭则跳过并记日志
            if last_final_text:
                if getattr(db, "is_active", True):
                    try:
                        rec = VisitRepo.get(db, visit_id)
                        if rec:
                            rec.conversation_transcript = (rec.conversation_transcript or "") + last_final_text + "\n"
                            db.commit()
                        logger.info("收尾兜底落库最后一句: visit_id=%s", visit_id)
                    except Exception as exc:
                        logger.error("收尾兜底落库失败: %s", exc)
                else:
                    logger.warning(
                        "会话已关闭，最后一句未落库（可用 end_visit 的 full_transcript 补齐）: visit_id=%s",
                        visit_id,
                    )
            try:
                async with send_lock:
                    await websocket.send_json({"type": "completed"})
            except Exception:
                pass  # 客户端已断开
    finally:
        db.close()
