"""Skill 模版管理（需求 3.6(4) 官方模版 + 4.7 代表侧广场）：
医学部创建 → 审核（受控查看 skill_weights + 访问审计）→ approved+is_public 上架广场。
隐私边界（附录B-1）：skill_weights 任何 API 不返回；公共广场仅元数据。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, success
from shared.models.skill import SkillAudit, SkillPackage
from shared.models.user import User

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/skill-packages", tags=["skill-packages"])

SKILL_ADMIN_ROLES = ("admin", "manager", "compliance", "medical")
VALID_AUDIT = ("pending", "approved", "rejected")


def _validate_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    name = (payload.get("name") or "").strip()
    if not name or len(name) > 100:
        raise ParamError("名称必填且不超过 100 字符")
    weights = payload.get("skill_weights")
    if not isinstance(weights, dict) or not weights:
        raise ParamError("skill_weights 必须是非空对象（沟通风格参数）")
    return {"name": name, "skill_weights": weights, "style_tags": payload.get("style_tags")}


def _validate_release_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    name = (payload.get("name") or "").strip()
    if not name or len(name) > 100:
        raise ParamError("名称必填且不超过 100 字符")
    description = (payload.get("description") or "").strip()
    if not description or len(description) > 200:
        raise ParamError("治疗领域/说明必填且不超过 200 字符")
    content = (payload.get("content") or "").strip()
    if not content:
        raise ParamError("Skill 内容（话术素材）不能为空")
    weights = payload.get("skill_weights")
    if not isinstance(weights, dict) or not weights:
        raise ParamError("skill_weights 必须是非空对象（沟通风格参数）")
    style_tags = payload.get("style_tags")
    if style_tags is not None and not isinstance(style_tags, list):
        raise ParamError("style_tags 必须是数组")
    return {
        "name": name, "description": description, "content": content,
        "skill_weights": weights, "style_tags": style_tags,
        "is_anonymous": bool(payload.get("is_anonymous", False)),
    }


@router.post("")
async def create_skill(
    payload: dict,
    current_user: dict = Depends(require_roles(*SKILL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    data = _validate_payload(payload)
    is_public = bool(payload.get("is_public", False))
    sk = SkillPackage(
        name=data["name"], creator_id=current_user["id"],
        is_public=is_public, is_anonymous=False, audit_status="pending",
        style_tags=data["style_tags"], heat=0,
        skill_weights=data["skill_weights"],
    )
    db.add(sk)
    db.commit()
    db.refresh(sk)
    await write_audit_log(
        action="skill_create",
        user_id=current_user["id"],
        resource_type="skill_package",
        resource_id=str(sk.id),
        after_value={"name": sk.name},
        request_id=get_request_id() or None,
    )
    return success(sk.to_dict())


@router.get("")
async def list_skills(
    page: int = 1,
    page_size: int = 20,
    audit_status: Optional[str] = None,
    current_user: dict = Depends(require_roles(*SKILL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    if audit_status and audit_status not in VALID_AUDIT:
        raise ParamError("audit_status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(SkillPackage)
    if audit_status:
        q = q.filter(SkillPackage.audit_status == audit_status)
    total = q.count()
    rows = q.order_by(SkillPackage.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([s.to_dict() for s in rows], total, p.page, p.page_size))


@router.get("/public")
async def public_plaza(
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """代表侧广场：仅 approved + is_public；无 skill_weights（隐私边界）"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(SkillPackage).filter(
        SkillPackage.is_public == True,  # noqa: E712
        SkillPackage.audit_status == "approved",
        SkillPackage.off_shelf_status == "active",
    )
    if keyword:
        q = q.filter(SkillPackage.name.ilike(f"%{keyword}%"))
    total = q.count()
    rows = q.order_by(SkillPackage.heat.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([s.to_dict() for s in rows], total, p.page, p.page_size))


@router.post("/release")
async def release_skill(
    payload: dict,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """三期 J：代表发布 Skill 到公共空间 → pending，审核通过后上代表侧广场。
    is_public=True（发布意图）；/public 广场按 audit_status=approved 过滤，pending 不可见。"""
    data = _validate_release_payload(payload)
    sk = SkillPackage(
        name=data["name"], creator_id=current_user["id"],
        description=data["description"], content=data["content"],
        is_public=True, is_anonymous=data["is_anonymous"],
        audit_status="pending", style_tags=data["style_tags"], heat=0,
        skill_weights=data["skill_weights"],
    )
    db.add(sk)
    db.commit()
    db.refresh(sk)
    await write_audit_log(
        action="skill_release", user_id=current_user["id"],
        resource_type="skill_package", resource_id=str(sk.id),
        after_value={"name": sk.name, "description": sk.description},
        request_id=get_request_id() or None,
    )
    return success(sk.to_dict())


@router.get("/mine")
async def my_skills(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """三期 J：代表查看本人发布 Skill（审核状态 + 热度数据 heat/approval_rate）。"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(SkillPackage).filter(SkillPackage.creator_id == current_user["id"])
    total = q.count()
    rows = q.order_by(SkillPackage.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([s.to_dict() for s in rows], total, p.page, p.page_size))


@router.get("/asset-list")
async def asset_list(
    page: int = 1,
    page_size: int = 20,
    audit_status: Optional[str] = None,
    off_shelf_status: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(require_roles(*SKILL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """三期 J：Skill 资产公共列表（含代表发布，元数据 + 创建者姓名/角色）。
    绝不含 content/skill_weights（隐私边界附录B-1）。"""
    if audit_status and audit_status not in VALID_AUDIT:
        raise ParamError("audit_status 不合法")
    if off_shelf_status and off_shelf_status not in ("active", "off_shelved"):
        raise ParamError("off_shelf_status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(SkillPackage).outerjoin(User, SkillPackage.creator_id == User.id)
    if audit_status:
        q = q.filter(SkillPackage.audit_status == audit_status)
    if off_shelf_status:
        q = q.filter(SkillPackage.off_shelf_status == off_shelf_status)
    if keyword:
        q = q.filter(SkillPackage.name.ilike(f"%{keyword}%"))
    total = q.count()
    rows = (
        q.order_by(SkillPackage.id.desc())
        .offset(p.offset).limit(p.limit)
        .with_entities(SkillPackage, User.full_name, User.role)
        .all()
    )
    items = []
    for sk, creator_name, creator_role in rows:
        d = sk.to_dict()
        d["creator_name"] = creator_name
        d["creator_role"] = creator_role
        items.append(d)
    return success(paginate(items, total, p.page, p.page_size))


@router.get("/{skill_id}/detail")
async def skill_detail(
    skill_id: int,
    current_user: dict = Depends(require_roles(*SKILL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """审核详情：受控查看 skill_weights（仅医学部等管理角色，隐私边界附录B-1）"""
    sk = db.query(SkillPackage).filter(SkillPackage.id == skill_id).first()
    if not sk:
        raise BusinessError("Skill 不存在", code=4001)
    await write_audit_log(
        action="skill_detail_view", user_id=current_user["id"],
        resource_type="skill_package", resource_id=str(sk.id),
        after_value={"name": sk.name},
        request_id=get_request_id() or None,
    )
    return success(sk.to_dict(expose_weights=True))


@router.post("/{skill_id}/review")
async def review_skill(
    skill_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*SKILL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """审核：approve/reject。审核人受控查看 skill_weights（读后写审计）。"""
    sk = db.query(SkillPackage).filter(SkillPackage.id == skill_id).first()
    if not sk:
        raise BusinessError("Skill 不存在", code=4001)
    if sk.audit_status != "pending":
        raise BusinessError("当前状态不可审核（仅待审核可审）", code=4001)
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    verdict = payload.get("verdict")
    if verdict not in ("approve", "reject"):
        raise ParamError("verdict 必须是 approve 或 reject")
    reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    if verdict == "reject" and not reason:
        raise ParamError("驳回必须填写原因")
    if len(reason) > 500:
        raise ParamError("原因长度不能超过 500 字符")
    sk.audit_status = "approved" if verdict == "approve" else "rejected"
    sk.audit_reason = reason if verdict == "reject" else None
    db.commit()
    db.refresh(sk)
    db.add(SkillAudit(
        skill_id=sk.id, auditor_id=current_user["id"],
        audit_result=sk.audit_status, reason=sk.audit_reason,
    ))
    db.commit()
    await write_audit_log(
        action="skill_review",
        user_id=current_user["id"],
        resource_type="skill_package",
        resource_id=str(sk.id),
        after_value={"audit_status": sk.audit_status, "audit_reason": sk.audit_reason},
        request_id=get_request_id() or None,
    )
    return success(sk.to_dict())


@router.post("/{skill_id}/load")
async def load_skill(
    skill_id: int,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """代表加载 Skill 到陪练场：仅 approved+is_public+active 可加载；heat++"""
    sk = db.query(SkillPackage).filter(
        SkillPackage.id == skill_id,
        SkillPackage.is_public == True,  # noqa: E712
        SkillPackage.audit_status == "approved",
        SkillPackage.off_shelf_status == "active",
    ).first()
    if not sk:
        raise BusinessError("该 Skill 不可加载（已下架或未通过审核）", code=4001)
    sk.heat = (sk.heat or 0) + 1
    db.commit()
    db.refresh(sk)
    return success(sk.to_dict())
