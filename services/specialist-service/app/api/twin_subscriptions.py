"""医生端分身订阅 + 分享链接激活（一期 B）

契约（2026-08-17 Task 6）：
- POST /api/v1/share-links/{token}/activate —— 任意登录；token 不存在/过期 → BusinessError 4001
  「链接不存在或已过期」；返回 {twin:{id,name,status}, subscribed, subscription_status}，
  twin 信息手写 dict（不含 bailian_app_id 等内部字段）。
- POST /api/v1/twin-subscriptions —— 任意登录；twin 必须 active（不存在/停用 → 4001）；
  consent_agreed != True → ParamError「须先签署知情同意」；已订阅同 twin → 幂等返回现有订阅
  （不重复写 consent）；新建写 DoctorConsent（version=CONSENT_VERSION, consent_type='twin'）
  + DoctorTwinSubscription（status=subscribed）；审计 action=twin_subscribe。
- GET /api/v1/twin-subscriptions —— 本人订阅列表（join Specialist，items = {subscription to_dict,
  twin_name, twin_status}）。
- POST /api/v1/twin-subscriptions/{twin_id}/toggle —— 只允许本人已存在的订阅行；审计
  action=twin_subscription_toggle。

知情同意语义注释：同代表多分身「不重复弹窗」由前端按 representative 维度控制，
后端只留痕每次 subscribe 的 consent 记录（不在此做跨 twin 去重）。
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.response import BusinessError, ParamError, success
from shared.models.doctor import DoctorConsent, DoctorTwinSubscription, ShareLink

from app.models.specialist import Specialist
from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["twin-subscriptions"])

CONSENT_VERSION = "1.0"


def _twin_info(specialist: Specialist) -> dict:
    """手写 twin 对外信息：只暴露 id/name/status，绝不带 bailian_app_id 等内部字段"""
    return {"id": specialist.id, "name": specialist.name, "status": specialist.status}


@router.post("/share-links/{token}/activate")
async def activate_share_link(
    token: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """激活分享链接：校验 token 有效期，返回 twin 信息 + 本人是否已订阅。

    token 不存在或已过期统一 4001「链接不存在或已过期」（不区分，防枚举）。
    """
    link = db.query(ShareLink).filter(ShareLink.url_token == token).first()
    if not link or (link.expire_at and link.expire_at < datetime.utcnow()):
        raise BusinessError("链接不存在或已过期", code=4001)

    specialist = db.query(Specialist).filter(Specialist.id == link.twin_id).first()
    if not specialist:
        raise BusinessError("链接不存在或已过期", code=4001)

    existing = db.query(DoctorTwinSubscription).filter(
        DoctorTwinSubscription.doctor_id == current_user["id"],
        DoctorTwinSubscription.twin_id == link.twin_id,
    ).first()

    return success({
        "twin": _twin_info(specialist),
        "subscribed": existing is not None,
        "subscription_status": existing.status if existing else None,
    })


@router.post("/twin-subscriptions")
async def subscribe_twin(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """订阅数字专员分身（须已签署知情同意）。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")

    twin_id = payload.get("twin_id")
    if isinstance(twin_id, bool) or not isinstance(twin_id, int):
        raise ParamError("twin_id 必须为整数")

    consent_agreed = payload.get("consent_agreed")
    if consent_agreed is not True:
        raise ParamError("须先签署知情同意")

    twin = db.query(Specialist).filter(Specialist.id == twin_id).first()
    if not twin or twin.status != "active":
        raise BusinessError("专员不存在或已停用", code=4001)

    existing = db.query(DoctorTwinSubscription).filter(
        DoctorTwinSubscription.doctor_id == current_user["id"],
        DoctorTwinSubscription.twin_id == twin_id,
    ).first()
    if existing:
        # 幂等：已订阅同 twin 直接返回现有订阅，不重复写 consent
        return success(existing.to_dict())

    sub = DoctorTwinSubscription(
        doctor_id=current_user["id"],
        twin_id=twin_id,
        status="subscribed",
        consent_version=CONSENT_VERSION,
        consent_at=datetime.utcnow(),
    )
    db.add(sub)
    # 每次 subscribe 留一条 consent 记录（同代表多分身去重由前端按 representative 维度控制）
    consent = DoctorConsent(
        doctor_id=current_user["id"],
        twin_id=twin_id,
        consent_type="twin",
        version=CONSENT_VERSION,
        agreed_at=datetime.utcnow(),
    )
    db.add(consent)
    db.commit()
    db.refresh(sub)

    await write_audit_log(
        user_id=current_user["id"], action="twin_subscribe",
        resource_type="doctor_twin_subscription", resource_id=str(sub.id),
        after_value=sub.to_dict(),
    )
    return success(sub.to_dict())


@router.get("/twin-subscriptions")
async def list_subscriptions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """本人订阅列表（join Specialist 补充 twin_name / twin_status）。"""
    rows = (
        db.query(DoctorTwinSubscription, Specialist)
        .outerjoin(Specialist, Specialist.id == DoctorTwinSubscription.twin_id)
        .filter(DoctorTwinSubscription.doctor_id == current_user["id"])
        .order_by(DoctorTwinSubscription.id)
        .all()
    )
    items = []
    for sub, twin in rows:
        item = sub.to_dict()
        item["twin_name"] = twin.name if twin else None
        item["twin_status"] = twin.status if twin else None
        items.append(item)
    return success(items)


@router.post("/twin-subscriptions/{twin_id}/toggle")
async def toggle_subscription(
    twin_id: int,
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """切换订阅状态（subscribed/blocked），只允许本人已存在的订阅行。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    status = payload.get("status")
    if status not in ("subscribed", "blocked"):
        raise ParamError("status 必须是 subscribed 或 blocked")

    sub = db.query(DoctorTwinSubscription).filter(
        DoctorTwinSubscription.doctor_id == current_user["id"],
        DoctorTwinSubscription.twin_id == twin_id,
    ).first()
    if not sub:
        raise BusinessError("订阅不存在", code=4001)

    sub.status = status
    db.commit()
    db.refresh(sub)

    await write_audit_log(
        user_id=current_user["id"], action="twin_subscription_toggle",
        resource_type="doctor_twin_subscription", resource_id=str(sub.id),
        after_value=sub.to_dict(),
    )
    return success(sub.to_dict())
