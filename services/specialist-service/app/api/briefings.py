"""分身夜间简报查询（一期 C）：代表端查看自己分身的每日简报"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, PermissionError, success
from shared.models.digital_specialist import Specialist
from shared.models.nightly_briefing import NightlyBriefing

router = APIRouter(prefix="/api/v1/briefings", tags=["briefings"])


def _require_rep(current_user: dict):
    if current_user["role"] != "rep":
        raise PermissionError("仅医药代表可查看夜间简报")


@router.get("")
async def list_briefings(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_rep(current_user)
    p = PaginationParams(page=page, page_size=page_size)
    query = (
        db.query(NightlyBriefing, Specialist)
        .join(Specialist, Specialist.id == NightlyBriefing.specialist_id)
        .filter(NightlyBriefing.representative_id == current_user["id"])
    )
    total = query.count()
    rows = query.order_by(NightlyBriefing.briefing_date.desc()).offset(p.offset).limit(p.limit).all()
    items = [{**b.to_dict(), "twin_name": s.name} for b, s in rows]
    return success(paginate(items, total, p.page, p.page_size))


@router.get("/{briefing_id}")
async def get_briefing(
    briefing_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_rep(current_user)
    row = (
        db.query(NightlyBriefing, Specialist)
        .join(Specialist, Specialist.id == NightlyBriefing.specialist_id)
        .filter(NightlyBriefing.id == briefing_id,
                NightlyBriefing.representative_id == current_user["id"])
        .first()
    )
    if not row:
        raise BusinessError("简报不存在", code=4000)
    b, s = row
    return success({**b.to_dict(), "twin_name": s.name})
