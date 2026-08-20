"""运营统计（需求 3.7(2)(3)）：医生活跃度 + 数字分身使用排行"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.response import success
from shared.models.digital_specialist import Specialist
from shared.models.doctor import DoctorTwinSubscription

from app.models.conversation import Conversation
from app.models.feedback import ConversationFeedback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/doctor-stats", tags=["doctor-stats"])

STATS_ADMIN_ROLES = ("admin", "manager", "compliance", "medical")


@router.get("/activity")
async def doctor_activity(
    _admin: dict = Depends(require_roles(*STATS_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """医生活跃度：日活/周活/月活（conversations 中 role='user' 且 user 为 doctor 的去重计数）"""
    from shared.models.user import User
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    def _count(since: datetime) -> int:
        return (
            db.query(sqlfunc.count(sqlfunc.distinct(Conversation.user_id)))
            .join(User, Conversation.user_id == User.id)
            .filter(
                Conversation.role == "user",
                Conversation.created_at >= since,
                User.role == "doctor",
            )
            .scalar()
        ) or 0

    return success({
        "dau": _count(day_ago),
        "wau": _count(week_ago),
        "mau": _count(month_ago),
    })


@router.get("/twin-ranking")
async def twin_ranking(
    _admin: dict = Depends(require_roles(*STATS_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """数字分身使用排行 Top10：服务医生数（订阅数）/好评率"""
    rows = db.query(Specialist).filter(Specialist.status == "active").limit(50).all()
    items = []
    for spec in rows:
        added = db.query(sqlfunc.count(DoctorTwinSubscription.id)).filter(
            DoctorTwinSubscription.twin_id == spec.id,
        ).scalar() or 0
        fb_total = db.query(sqlfunc.count(ConversationFeedback.id)).filter(
            ConversationFeedback.specialist_id == spec.id,
        ).scalar() or 0
        fb_pos = db.query(sqlfunc.count(ConversationFeedback.id)).filter(
            ConversationFeedback.specialist_id == spec.id,
            ConversationFeedback.rating == 1,
        ).scalar() or 0
        approval = round(fb_pos / fb_total, 4) if fb_total else None
        items.append({
            "twin_id": spec.id, "name": spec.name, "status": spec.status,
            "added_count": added, "approval_rate": approval,
        })
    items.sort(key=lambda x: x["added_count"], reverse=True)
    return success({"items": items[:10]})
