"""数字专员对话 WebSocket 端点（流式）

协议（见 docs/superpowers/specs/2026-08-06-gap-closure-batch2-design.md 3.1）：
    客户端 → {"type":"question","text","session_id"} / {"type":"stop"}
    服务端 → start → delta* → done；异常 error（关 4500）；token 无效关 4401
send 统一加锁，防 websockets>=12 ConcurrencyError（沿用 asr_ws.py send_lock 模式）。
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from sqlalchemy.orm import Session

from shared.common.auth import verify_token
from shared.common.db_session import get_db
from app.core.answer_generator import AnswerGenerator
from app.api.conversations import assert_session_owner

router = APIRouter(tags=["chat-ws"])
logger = logging.getLogger(__name__)

# 生成器工厂（测试注入用）
_generator_factory = lambda: AnswerGenerator()


def get_generator_factory():
    return _generator_factory


def set_generator_factory(fn):
    global _generator_factory
    _generator_factory = fn


def _get_specialist(db, specialist_id: int):
    """校验专员存在（与 REST 语义一致：id + active）；不存在返回 None。

    抽成模块函数便于测试 monkeypatch（WS 依赖不走 Depends，注入 DB 会话不可行）。
    """
    from app.models.specialist import Specialist
    return db.query(Specialist).filter(
        Specialist.id == specialist_id,
        Specialist.status == "active",
    ).first()


@router.websocket("/ws/specialists/{specialist_id}/chat")
async def chat_ws(
    websocket: WebSocket,
    specialist_id: int,
    db: Session = Depends(get_db),
):
    token = websocket.query_params.get("token", "")
    try:
        payload = verify_token(token)
    except HTTPException:
        await websocket.close(code=4401)
        return
    user_id = int(payload["sub"])

    specialist = _get_specialist(db, specialist_id)
    if not specialist:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    send_lock = asyncio.Lock()

    async def send(frame: dict):
        async with send_lock:
            await websocket.send_text(json_dumps(frame))

    # 读客户端首帧 question（60s 内未发则关 4500）
    question = None
    session_id = None
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=60)
        msg = json.loads(raw)
        if msg.get("type") == "question":
            question = (msg.get("text") or "").strip()
            session_id = msg.get("session_id")
        elif msg.get("type") == "stop":
            await websocket.close(code=4500)
            return
    except (WebSocketDisconnect, Exception):
        await websocket.close(code=4500)
        return
    if not question:
        await send({"type": "error", "message": "question 不能为空"})
        await websocket.close(code=4500)
        return

    # IDOR 防护：question 帧带 session_id 时校验归属，续传他人会话关 4404（不泄露存在性）
    if session_id:
        try:
            assert_session_owner(db, session_id, user_id)
        except HTTPException:
            await send({"type": "error", "message": "无权访问该会话"})
            await websocket.close(code=4404)
            return

    generator = get_generator_factory()()
    stop_event = asyncio.Event()

    async def client_loop():
        """接收客户端消息：stop → 中止生成"""
        try:
            while not stop_event.is_set():
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                if msg.get("type") == "stop":
                    stop_event.set()
        except Exception:
            pass  # 连接断开

    client_task = asyncio.create_task(client_loop())

    # 开始生成（start 帧不带 request_id：该值在 generate_stream 内部生成，客户端以 type 为准）
    await send({"type": "start"})
    result = None
    try:
        async for frame in generator.generate_stream(
            question=question,
            specialist=specialist,
            user_id=user_id,
            session_id=session_id,
        ):
            if stop_event.is_set():
                break
            if frame["type"] == "delta":
                await send({"type": "delta", "text": frame["text"]})
            elif frame["type"] == "done":
                result = frame
                break
    except Exception as e:
        logger.exception(f"[chat_ws] 生成异常: {e}")
        await send({"type": "error", "message": "生成失败，请稍后重试"})
        await websocket.close(code=4500)
        return
    finally:
        client_task.cancel()

    if result is None:
        await send({"type": "error", "message": "生成中断"})
        await websocket.close(code=4500)
        return

    # 落库（复用 REST 的 _persist_conversation，使用注入的 db 会话）
    from app.api.specialists import _persist_conversation
    conversation_id = _persist_conversation(
        db, user_id, specialist_id, question,
        {
            "session_id": result.get("session_id"),
            "answer": result.get("answer"),
            "citations": result.get("citations"),
            "blocked": result.get("blocked"),
            "latency_ms": result.get("latency_ms"),
        },
    )

    await send({
        "type": "done",
        "text": result.get("answer", ""),
        "answer": result.get("answer", ""),  # 兼容字段：协议以 text 为准，answer 同步冗余
        "session_id": result.get("session_id"),
        "conversation_id": conversation_id,
        "citations": result.get("citations", []),
        "blocked": result.get("blocked", False),
        "violations": result.get("violations", []),
        "evidence_level": result.get("evidence_level"),
        "latency_ms": result.get("latency_ms"),
    })
    await websocket.close(code=1000)


def json_dumps(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)
