"""对话反馈 / 收藏 / 我的收藏"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import ParamError, success
from shared.common.conventions import not_prep_session

from app.models.conversation import Conversation
from app.models.feedback import ConversationFeedback
from app.models.favorite import ConversationFavorite

# 注意：/conversations/{conversation_id}/... 与 /favorites 路径存在歧义，
# 收藏列表/删除单独挂在 favorites_router（prefix=/api/v1/favorites）上。
router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
favorites_router = APIRouter(prefix="/api/v1/favorites", tags=["favorites"])
logger = logging.getLogger(__name__)


def _get_conv_or_404(db: Session, conv_id: int) -> Conversation:
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


def _assert_conv_owner(conv: Conversation, current_user: dict):
    if conv.user_id != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权操作该对话")


def assert_session_owner(db: Session, session_id: str, user_id: int):
    """校验会话归属（IDOR 防护）：conversations 表中该 session 至少有一条属于该用户。

    他人会话 → 404（统一 404 不泄露 session 是否存在）；session_id 为空直接通过
    （新建会话）；**库里尚无任何行的 session 也放行**（视为新会话标签——
    visit-service prepare_visit 以 visit_prep_ 前缀新开机器会话依赖此语义；
    uuid 不可猜，放行空会话不削弱"他人已有会话 404"的保护）。
    会话历史读取 / REST chat 续传 / WS question 帧续传共用此校验。
    """
    if not session_id:
        return
    any_row = db.query(Conversation).filter(
        Conversation.session_id == session_id,
    ).first()
    if any_row is None:
        return  # 空会话 = 新建
    owned = db.query(Conversation).filter(
        Conversation.session_id == session_id,
        Conversation.user_id == user_id,
    ).first()
    if not owned:
        raise HTTPException(status_code=404, detail="会话不存在")


@router.get("/search")
async def search_conversations(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    user_id: Optional[int] = None,
    specialist_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_prep: bool = False,
    _admin: dict = Depends(require_roles("admin", "manager", "compliance")),
    db: Session = Depends(get_db),
):
    """对话日志全文检索（二期 E，需求 3.2(1)）：admin/manager/compliance。

    按 代表(user_id) / 分身(specialist_id) / 时间范围 / 命中词 筛选；
    返回每条命中 + 该会话完整上下文（session_id 全部行，role/content）。
    默认排除 visit_prep_ 机器会话（拜访准备的系统指令非真人提问，
    混入检索结果会误导审核）；include_prep=true 可查看排查。
    """
    from datetime import datetime
    from shared.common.response import ParamError as PE

    def _parse(s: Optional[str], name: str) -> Optional[datetime]:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            raise PE(f"{name} 格式应为 ISO 时间")

    q = db.query(Conversation)
    if not include_prep:
        q = q.filter(not_prep_session(Conversation.session_id))
    if keyword:
        q = q.filter(Conversation.content.ilike(f"%{keyword}%"))
    if user_id:
        q = q.filter(Conversation.user_id == user_id)
    if specialist_id:
        q = q.filter(Conversation.specialist_id == specialist_id)
    if date_from:
        q = q.filter(Conversation.created_at >= _parse(date_from, "date_from"))
    if date_to:
        q = q.filter(Conversation.created_at <= _parse(date_to, "date_to"))

    total = q.count()
    rows = q.order_by(Conversation.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for conv in rows:
        ctx_rows = db.query(Conversation).filter(
            Conversation.session_id == conv.session_id
        ).order_by(Conversation.id.asc()).all()
        items.append({
            "id": conv.id,
            "user_id": conv.user_id,
            "specialist_id": conv.specialist_id,
            "session_id": conv.session_id,
            "role": conv.role,
            "content": conv.content,
            "blocked": bool(conv.compliance_result and conv.compliance_result.get("blocked")),
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "context": [{
                "role": c.role, "content": c.content,
                "blocked": bool(c.compliance_result and c.compliance_result.get("blocked")),
            } for c in ctx_rows],
        })
    return success(paginate(items, total=total, page=page, page_size=page_size))


@router.post("/{conversation_id}/feedback")
async def submit_feedback(
    conversation_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """点赞/点踩：{"rating": 1|-1, "comment": "可选"}"""
    rating = request.get("rating")
    if rating not in (1, -1):
        raise ParamError("rating 必须是 1（赞）或 -1（踩）")
    conv = _get_conv_or_404(db, conversation_id)
    _assert_conv_owner(conv, current_user)
    # M-4（2026-08-24 审查修复）：upsert —— 同一用户对同一对话只有一条反馈，
    # 改主意覆盖原 rating/comment。此前每次 POST 都插新行，rating==1 的
    # approval_rate 聚合可被无限点赞注水（DB 侧 uq_feedback_user_conversation 兜底）
    fb = db.query(ConversationFeedback).filter(
        ConversationFeedback.conversation_id == conv.id,
        ConversationFeedback.user_id == current_user["id"],
    ).first()
    if fb:
        fb.rating = rating
        fb.comment = (request.get("comment") or "")[:500]
    else:
        fb = ConversationFeedback(
            conversation_id=conv.id,
            user_id=current_user["id"],
            specialist_id=conv.specialist_id,
            rating=rating,
            comment=(request.get("comment") or "")[:500],
        )
        db.add(fb)
    db.commit()
    logger.info("feedback saved: user=%s conv=%s rating=%s", current_user["id"], conv.id, rating)
    return success({"feedback_id": fb.id})


@router.post("/{conversation_id}/favorite")
async def toggle_favorite(
    conversation_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """收藏/取消收藏（toggle，无 body）"""
    conv = _get_conv_or_404(db, conversation_id)
    _assert_conv_owner(conv, current_user)
    existing = db.query(ConversationFavorite).filter(
        ConversationFavorite.user_id == current_user["id"],
        ConversationFavorite.conversation_id == conv.id,
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
        return success({"is_favorite": False})
    # 快照同轮问答（多轮修复）：收藏的是 assistant 答案行时，answer=该行内容、
    # question=同 session 内该答案之前最后一条 user 行（按 id 序，且过滤
    # id <= conv.id，防止快照到后续轮次）；收藏到 user 行时镜像处理。
    msgs = db.query(Conversation).filter(
        Conversation.session_id == conv.session_id,
        Conversation.id <= conv.id,
    ).order_by(Conversation.id).all() if conv.session_id else [conv]
    if conv.role == "assistant":
        answer = conv.content
        citations = conv.citations
        question = next((m.content for m in reversed(msgs) if m.role == "user"), conv.content)
    else:
        question = conv.content
        answer_conv = next((m for m in reversed(msgs) if m.role == "assistant"), None)
        answer = answer_conv.content if answer_conv else ""
        citations = answer_conv.citations if answer_conv else None
    fav = ConversationFavorite(
        conversation_id=conv.id,
        user_id=current_user["id"],
        specialist_id=conv.specialist_id,
        question=question,
        answer=answer,
        citations=citations,
    )
    db.add(fav)
    try:
        db.commit()
    except IntegrityError:
        # D4（2026-08-13）：并发双点 toggle —— check-then-insert 竞态下第二个
        # 请求撞 (user_id, conversation_id) 唯一约束。此时该收藏已由并发请求
        # 写入，最终态即"已收藏"，按幂等成功返回，防 500。
        db.rollback()
        return success({"is_favorite": True})
    return success({"is_favorite": True})


def compute_satisfaction(positive: int, negative: int) -> dict:
    """满意度统计（纯函数）。

    satisfaction_rate 语义为 0-100 百分数（web 直接显示 %），
    无反馈时返回 None。0.0~1.0 旧语义已在 2026-08-06 对齐为 0-100。
    """
    total = positive + negative
    if total == 0:
        return {"total_feedback": 0, "satisfaction_rate": None}
    return {"total_feedback": total, "satisfaction_rate": round(positive / total * 100)}


@favorites_router.get("")
async def list_favorites(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的收藏列表"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(ConversationFavorite).filter(ConversationFavorite.user_id == current_user["id"])
    total = q.count()
    items = q.order_by(ConversationFavorite.created_at.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([{
        "id": f.id, "conversation_id": f.conversation_id, "specialist_id": f.specialist_id,
        "question": f.question, "answer": f.answer, "citations": f.citations,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    } for f in items], total=total, page=p.page, page_size=p.page_size))


@favorites_router.delete("/{favorite_id}")
async def remove_favorite(
    favorite_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消收藏"""
    fav = db.query(ConversationFavorite).filter(ConversationFavorite.id == favorite_id).first()
    if not fav:
        raise HTTPException(status_code=404, detail="收藏不存在")
    if fav.user_id != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权操作该收藏")
    db.delete(fav)
    db.commit()
    return success(None, "已取消收藏")
