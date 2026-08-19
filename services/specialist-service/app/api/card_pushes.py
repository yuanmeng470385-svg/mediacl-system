"""医生端学术卡片接收/阅读追踪/反馈 + 站内通知查询（二期 G）"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, success
from shared.models.academic import AcademicCard, CardPushRecord, Notification

from app.models.feedback import ConversationFeedback
from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/card-pushes", tags=["card-pushes"])

VALID_STATUS = ("unread", "read", "favorited", "forwarded")


@router.get("")
async def doctor_inbox(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """医生端收件箱：本人收到的学术卡片（带卡片内容）"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(CardPushRecord).filter(CardPushRecord.doctor_id == current_user["id"])
    total = q.count()
    rows = q.order_by(CardPushRecord.id.desc()).offset(p.offset).limit(p.limit).all()
    items = []
    for r in rows:
        card = db.query(AcademicCard).filter(AcademicCard.id == r.card_id).first()
        item = r.to_dict()
        item["card"] = card.to_dict() if card else None
        items.append(item)
    return success(paginate(items, total, p.page, p.page_size))


@router.post("/{push_id}/track")
async def track_read(
    push_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """阅读追踪：read_status + 停留秒数（医生端离开卡片时上报）"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    rec = db.query(CardPushRecord).filter(CardPushRecord.id == push_id).first()
    if not rec or rec.doctor_id != current_user["id"]:
        raise BusinessError("推送记录不存在", code=4001)
    status = payload.get("read_status")
    if status and status not in VALID_STATUS:
        raise ParamError("read_status 不合法")
    if status:
        rec.read_status = status
        rec.read_at = __import__("datetime").datetime.utcnow()
    seconds = payload.get("seconds")
    if isinstance(seconds, int) and seconds > 0:
        rec.tracked_seconds = seconds
    db.commit()
    db.refresh(rec)
    return success(rec.to_dict())


@router.post("/{push_id}/feedback")
async def submit_feedback(
    push_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """医生反馈：useful / useless / 追问文本（回流代表简报）"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    feedback = payload.get("feedback")
    if not feedback or not isinstance(feedback, str) or len(feedback) > 500:
        raise ParamError("feedback 必填且不超过 500 字符")
    rec = db.query(CardPushRecord).filter(CardPushRecord.id == push_id).first()
    if not rec or rec.doctor_id != current_user["id"]:
        raise BusinessError("推送记录不存在", code=4001)
    was_useful = rec.feedback == "useful"
    rec.feedback = feedback
    if feedback in ("useful", "useless"):
        rec.read_status = "favorited" if feedback == "useful" else "read"
    # 有用反馈：累加该分身好评计数，同步至管理后台统计（spec 6.3）
    # monitor 的 approval_rate 按 conversation_feedback.rating==1 聚合，此处写一条
    # 卡片好评记录（rating=1，comment='学术卡片有用'），无需改 monitor。同一 push 仅
    # 首次 useful 写入，重复 useful 不重复累加。
    if feedback == "useful" and rec.specialist_id and not was_useful:
        db.add(ConversationFeedback(
            conversation_id=None,
            user_id=rec.doctor_id,
            specialist_id=rec.specialist_id,
            rating=1,
            comment="学术卡片有用",
        ))
    db.commit()
    db.refresh(rec)
    # 通知回流代表
    db.add(Notification(
        user_id=rec.representative_id,
        type="card_question" if feedback not in ("useful", "useless") else "card_feedback",
        title="医生反馈" if feedback in ("useful", "useless") else "医生追问",
        content=feedback,
        link=f"/briefings",
    ))
    db.commit()
    return success(rec.to_dict())


@router.get("/notifications")
async def list_notifications(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("rep", "doctor")),
    db: Session = Depends(get_db),
):
    """站内通知（代表端简报就绪/反馈回流，医生端新卡片）"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(Notification).filter(Notification.user_id == current_user["id"])
    total = q.count()
    rows = q.order_by(Notification.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([n.to_dict() for n in rows], total, p.page, p.page_size))
