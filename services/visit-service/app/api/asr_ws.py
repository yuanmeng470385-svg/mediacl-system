"""实时转写 WebSocket 端点（移动端录音推流 → NLS 流式识别 → 增量回推）

    WS  /ws/visits/{visit_id}/asr?token=<JWT>

移动端连上后：
  1. 以 Binary Frame 推送 PCM 音频（16k/16bit/单声道）
  2. 服务端转发 NLS 实时语音识别，逐句回推 JSON（speaker 字段：NLS 实时识别
     不支持说话人分离（2026-08-27 文档确认），缺省 "rep"；双方分离由移动端
     手动标注，经 REST transcript 提交 speaker）：
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
import time
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.exceptions import HTTPException
from websockets.exceptions import ConcurrencyError, ConnectionClosed

from shared.common.auth import verify_token
from shared.common.db_session import SessionLocal
from shared.models.user import User

from app.db.repositories.visit_repo import VisitRepo
from app.services.realtime_asr import MockRealtimeAsrClient, RealtimeAsrClient
from app.constants import AI_SUMMARY_PLACEHOLDER, VISIT_STATUS_CANCELLED

router = APIRouter(tags=["asr"])
logger = logging.getLogger(__name__)

# ==================== M14（2026-08-14）：直连 8002 的防御性限制 ====================
# ASR WS 不走网关（网关不支持 WS 升级透传），天然绕过网关限流 —— 每条连接会
# 拉起一条 NLS 付费会话 + conversation_transcript 无限追加 + 无界并发合规调用。
# 以下限制为单进程近似防护：模块级计数器只覆盖本 worker（多 worker 部署时各
# worker 各自计数，跨 worker 的精确控制可后续引入 Redis 分布式计数，与网关
# 限流同模式）。计数增删之间无 await（asyncio 单线程内原子），无需加锁。
MAX_ASR_CONNECTIONS = 10             # 全局并发 ASR 会话上限
MAX_ASR_CONNECTIONS_PER_USER = 2     # 同一用户并发 ASR 会话上限（防单账号刷 NLS 会话）
MAX_FRAME_BYTES = 256 * 1024         # 单帧字节上限（PCM 分片 16KB，正常远小于此）
ASR_IDLE_TIMEOUT_SECONDS = 90.0      # 空闲超时：无任何帧即关闭（移动端录音中每 2s 推流，90s 宽松）
ASR_SESSION_MAX_SECONDS = 6 * 3600   # 会话时长上限（防僵尸连接挂住 NLS 会话）

_asr_conn_count = 0                  # 全局并发 ASR 会话计数
_asr_conn_by_user: Dict[int, int] = {}  # user_id -> 并发 ASR 会话计数


async def _send_error_frame(websocket: WebSocket, send_lock: asyncio.Lock, message: str,
                            close_code: Optional[int] = None) -> None:
    """best-effort error 帧推送（可附带关闭码）：客户端可能已断开/发送竞争，失败仅吞掉不炸

    终审低3（2026-08-14）：close 帧同样是写帧 —— 与后台 _check_later 的 compliance
    帧并发写会交错（websockets 并发写帧竞态，正是 send_lock 要防的）。close 与
    error 帧在同一锁内发出保证帧序（error 先于 close，中间不被合规帧插入）；close
    抛异常（客户端已断开）一并吞掉，不丢关闭码语义、不影响收尾 finally 递减计数。
    """
    try:
        async with send_lock:
            await websocket.send_json({"type": "error", "message": message})
            if close_code is not None:
                await websocket.close(code=close_code)
    except Exception:
        pass


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
    global _asr_conn_count, _asr_conn_by_user  # M14：函数内 += 需显式声明全局
    # ---- 鉴权：先 accept（accept 前 close 的 4401/4403/4404 到不了客户端），
    #      再收首帧 —— B5 首帧鉴权（2026-08-12）：首帧 {"type":"auth","token"} 优先；
    #      旧客户端（query token）首帧即音频/stop → 回退 query，缓存该帧继续处理 ----
    token = websocket.query_params.get("token", "")
    await websocket.accept()
    first_frame = None
    try:
        raw_first = await asyncio.wait_for(websocket.receive(), timeout=10)
        if raw_first.get("type") == "websocket.disconnect":
            await websocket.close(code=4401)
            return
        if raw_first.get("text"):
            try:
                first_msg = json.loads(raw_first["text"])
            except json.JSONDecodeError:
                first_msg = {}
            if first_msg.get("type") == "auth" and first_msg.get("token"):
                token = str(first_msg["token"])
            else:
                first_frame = raw_first  # 旧客户端：首帧即协议帧（stop/其他），缓存
        else:
            first_frame = raw_first  # 旧客户端：首帧即 PCM 音频分片
    except Exception:
        await websocket.close(code=4401)
        return

    try:
        payload = verify_token(token)
    except HTTPException:
        await websocket.close(code=4401)  # 未认证
        return
    user_id = int(payload["sub"])

    # ---- 归属校验（S4）：仅本人或 admin ----
    db = SessionLocal()
    registered = False  # M14：通过连接数上限检查并登记后才置 True（finally 递减）
    try:
        # H2（2026-08-11）：账号状态与角色以库为准——token 是登录快照，停用/降级后
        # 旧 token 必须立即失效（WS 不走 get_current_user 依赖），admin 判定不再
        # 信 token 里的 role 快照（被降级 admin 的旧 token 不能跨用户读转写）
        user = db.query(User).filter(User.id == user_id, User.status == "active").first()
        if not user:
            await websocket.close(code=4401)  # 账号不存在或已停用
            return
        role = user.role
        record = VisitRepo.get(db, visit_id)
        if not record:
            await websocket.close(code=4404)  # 拜访不存在
            return
        if record.user_id != user_id and role != "admin":
            await websocket.close(code=4403)  # 无权
            return
        # B4（2026-08-13）：连接建立即查拜访状态 —— 已结束/已取消直接 error 帧 +
        # 关闭，不开付费 NLS 会话（误连已封存证据的拜访既烧钱又无意义；与 F12
        # 同口径：占位串不算已结束，可重试 end 的拜访仍允许连接）
        if record.status == VISIT_STATUS_CANCELLED:
            await websocket.send_json({"type": "error", "message": "拜访已取消，不能开始实时转写"})
            await websocket.close(code=4404)
            return
        if record.ai_summary and record.ai_summary != AI_SUMMARY_PLACEHOLDER:
            await websocket.send_json({"type": "error", "message": "拜访已结束，不能开始实时转写"})
            await websocket.close(code=4404)
            return
        # 串行化该连接的所有 send：后台合规任务与主路径并发 send 会触发
        # websockets>=12 的 ConcurrencyError（事件被吞、合规拦截丢失）
        send_lock = asyncio.Lock()

        # ---- M14 连接级限制：在开 NLS 会话（_get_asr_client）前检查 ----
        # 超限发 error 帧 + 4500 关闭（与"服务端未配置"同一关闭码语义）。
        # Mock 客户端路径同样受此限制（Mock 不花钱，但无界连接同样拖垮服务，
        # 连接数限制对两者都生效合理）。
        if _asr_conn_count >= MAX_ASR_CONNECTIONS:
            logger.warning("ASR 并发会话已达上限，拒绝新连接: visit_id=%s", visit_id)
            await _send_error_frame(websocket, send_lock, "并发转写会话已达上限，请稍后再试")
            await websocket.close(code=4500)
            return
        user_conns = _asr_conn_by_user.get(user_id, 0)
        if user_conns >= MAX_ASR_CONNECTIONS_PER_USER:
            logger.warning("用户 ASR 并发会话已达上限，拒绝新连接: visit_id=%s user_id=%s", visit_id, user_id)
            await _send_error_frame(websocket, send_lock, "当前账号的并发转写会话已达上限")
            await websocket.close(code=4500)
            return
        _asr_conn_count += 1
        _asr_conn_by_user[user_id] = user_conns + 1
        registered = True

        async with send_lock:
            await websocket.send_json({"type": "ready", "visit_id": visit_id})

        try:
            asr, is_mock = _get_asr_client()
        except RuntimeError as exc:
            async with send_lock:
                await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=4500)  # 服务端未配置
            return

        # 2026-08-27：ASR 只回推转写帧不落库（落库统一走前端 REST 带 speaker），
        # 会话收尾只回推 completed 帧 —— 无落库缓冲
        async def on_sentence(text: str, index: int, is_final: bool, speaker=None):
            # 回推增量/断句给 App（统一携带 speaker 字段：NLS 不支持分离，缺省 rep，
            # 真实说话人由移动端手动标注经 REST transcript 提交）。
            # send 失败（客户端断开/发送竞争/连接关闭后 starlette send 抛 RuntimeError）
            # 不中断转写处理 —— 与 _check_later 同一容错模式，失败仅跳过推送
            try:
                async with send_lock:
                    await websocket.send_json({
                        "type": "sentence", "index": index, "text": text, "final": is_final,
                        "speaker": _map_speaker(speaker),
                    })

            except (ConcurrencyError, ConnectionClosed, RuntimeError):
                logger.info("客户端已断开或发送竞争，跳过断句推送")
            # 2026-08-27 双方分离重构：ASR WS 不再直接落库/做合规 —— 此前 final 句
            # 在 WS 端落库（无 speaker 前缀、speaker 不分、医生话也判违规），前端 REST
            # 带 speaker 的提交被 F5 去重跳过 → 手动标注完全失效。落库+合规统一走前端
            # REST sendTranscript（带 speaker：医生话跳过代表合规、落库 [医生] 前缀）。
            # ASR WS 只负责转写回推（sentence/completed 帧）。

        await asr.start(on_sentence=on_sentence)

        # 首帧缓存（旧客户端首帧即音频/stop，已在鉴权段接收）先于循环消费
        pending_frames = [first_frame] if first_frame is not None else []
        session_start = time.monotonic()  # M14：会话时长上限起点
        try:
            while True:
                if pending_frames:
                    frame = pending_frames.pop(0)
                else:
                    # M14：空闲超时 + 会话时长上限 —— 每次 receive 挂超时
                    # （wait_for 与既有接收循环同构，无独立看门狗任务、无竞态）；
                    # 移动端录音中每 2s 推流，90s 空闲阈值足够宽松
                    remaining = ASR_SESSION_MAX_SECONDS - (time.monotonic() - session_start)
                    if remaining <= 0:
                        await _send_error_frame(websocket, send_lock, "转写会话时长已达上限", close_code=4500)
                        break
                    try:
                        frame = await asyncio.wait_for(
                            websocket.receive(),
                            timeout=min(ASR_IDLE_TIMEOUT_SECONDS, remaining),
                        )
                    except asyncio.TimeoutError:
                        if ASR_SESSION_MAX_SECONDS - (time.monotonic() - session_start) <= 0:
                            message = "转写会话时长已达上限"
                        else:
                            message = "空闲超时，转写会话已关闭"
                        logger.info("ASR 会话关闭: visit_id=%s reason=%s", visit_id, message)
                        await _send_error_frame(websocket, send_lock, message, close_code=4500)
                        break
                if frame.get("type") == "websocket.disconnect":
                    break
                data = frame.get("bytes") or frame.get("text")
                if not data:
                    continue
                # M14：帧大小上限 —— 超限发 error 帧并关闭（PCM 分片 16KB 正常远小于此）
                if len(data) > MAX_FRAME_BYTES:
                    logger.warning("ASR 超帧拒绝并关闭: visit_id=%s size=%d", visit_id, len(data))
                    await _send_error_frame(websocket, send_lock, "音频帧超过大小上限", close_code=4500)
                    break
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
            # 2026-08-27：ASR 不落库（落库统一走前端 REST sendTranscript 带 speaker），
            # 会话收尾只回推 completed 帧。
            try:
                async with send_lock:
                    await websocket.send_json({"type": "completed"})
            except Exception:
                pass  # 客户端已断开
    finally:
        # M14：无论正常结束/断开/异常，登记的并发计数都递减（登记点之后
        # 的任何 return 都被本 finally 覆盖）
        if registered:
            _asr_conn_count -= 1
            left = _asr_conn_by_user.get(user_id, 0) - 1
            if left <= 0:
                _asr_conn_by_user.pop(user_id, None)
            else:
                _asr_conn_by_user[user_id] = left
        db.close()
