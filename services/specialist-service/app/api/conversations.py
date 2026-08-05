"""对话反馈 / 收藏 / 我的收藏"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import ParamError, success

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
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """收藏/取消收藏（toggle）"""
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
    # 快照问题与答案（conversation 里 user 行是问题、assistant 行是答案，取同 session 两条）
    msgs = db.query(Conversation).filter(
        Conversation.session_id == conv.session_id
    ).order_by(Conversation.created_at).all() if conv.session_id else [conv]
    question = next((m.content for m in msgs if m.role == "user"), conv.content)
    answer = next((m.content for m in msgs if m.role == "assistant"), "")
    fav = ConversationFavorite(
        conversation_id=conv.id,
        user_id=current_user["id"],
        specialist_id=conv.specialist_id,
        question=question,
        answer=answer,
        citations=conv.citations,
    )
    db.add(fav)
    db.commit()
    return success({"is_favorite": True})


def compute_satisfaction(positive: int, negative: int) -> dict:
    """满意度统计（纯函数）"""
    total = positive + negative
    if total == 0:
        return {"total_feedback": 0, "satisfaction_rate": None}
    return {"total_feedback": total, "satisfaction_rate": round(positive / total, 4)}


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
