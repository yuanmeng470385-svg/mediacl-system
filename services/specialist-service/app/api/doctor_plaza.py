"""医生侧公共广场（需求 5.6）：官方公共数字员工浏览/添加（知情同意）+ 热门排行"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, success
from shared.models.digital_specialist import Specialist
from shared.models.doctor import DoctorConsent, DoctorTwinSubscription

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/doctor-plaza", tags=["doctor-plaza"])


@router.get("")
async def plaza_list(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """官方公共数字员工列表（仅 is_official + active）+ 热门排行（被添加数）"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(Specialist).filter(
        Specialist.is_official == True,  # noqa: E712
        Specialist.status == "active",
    )
    total = q.count()
    rows = q.order_by(Specialist.id.desc()).offset(p.offset).limit(p.limit).all()
    items = []
    for spec in rows:
        added = db.query(sqlfunc.count(DoctorTwinSubscription.id)).filter(
            DoctorTwinSubscription.twin_id == spec.id,
        ).scalar() or 0
        item = spec.to_dict()
        item["added_count"] = added
        items.append(item)
    return success(paginate(items, total, p.page, p.page_size))


@router.post("/{twin_id}/subscribe")
async def subscribe_plaza_twin(
    twin_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """添加官方公共数字员工：知情同意 + 写订阅（需求 5.6(2) 添加前知情同意确认）"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    if not payload.get("consent"):
        raise ParamError("须确认知情同意后才能添加")
    spec = db.query(Specialist).filter(
        Specialist.id == twin_id,
        Specialist.is_official == True,  # noqa: E712
        Specialist.status == "active",
    ).first()
    if not spec:
        raise BusinessError("该官方数字员工不可添加", code=4001)
    existing = db.query(DoctorTwinSubscription).filter_by(
        doctor_id=current_user["id"], twin_id=twin_id,
    ).first()
    if existing:
        return success(existing.to_dict())  # 已添加幂等
    sub = DoctorTwinSubscription(
        doctor_id=current_user["id"], twin_id=twin_id,
        status="subscribed", consent_version="1.0",
        consent_at=__import__("datetime").datetime.utcnow(),
    )
    db.add(sub)
    db.add(DoctorConsent(
        doctor_id=current_user["id"], twin_id=twin_id,
        consent_type="twin", version="1.0",
        agreed_at=__import__("datetime").datetime.utcnow(),
    ))
    db.commit()
    db.refresh(sub)
    await write_audit_log(
        action="doctor_plaza_subscribe",
        user_id=current_user["id"], resource_type="digital_specialist",
        resource_id=str(twin_id), request_id=get_request_id() or None,
    )
    return success(sub.to_dict())
