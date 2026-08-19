"""培训材料管理（需求文档 3.4(1)）：医学部/合规部创建维护，代表端只读"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, PermissionError, success
from shared.models.training_exam import TrainingMaterial

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/training-materials", tags=["training-materials"])

MATERIAL_ADMIN_ROLES = ("admin", "manager", "compliance", "medical")
VALID_TYPES = ("regulation", "rdpac", "internal")


def _validate_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    title = (payload.get("title") or "").strip()
    if not title:
        raise ParamError("标题不能为空")
    if len(title) > 200:
        raise ParamError("标题长度不能超过 200 字符")
    content = payload.get("content")
    if not content or not str(content).strip():
        raise ParamError("材料正文不能为空")
    material_type = (payload.get("material_type") or "").strip()
    if material_type not in VALID_TYPES:
        raise ParamError("material_type 必须是 regulation/rdpac/internal 之一")
    return {"title": title, "content": str(content).strip(), "material_type": material_type}


@router.post("")
async def create_material(
    payload: dict,
    current_user: dict = Depends(require_roles(*MATERIAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """创建培训材料（医学部/合规部/admin/manager）"""
    data = _validate_payload(payload)
    mat = TrainingMaterial(**data, created_by=current_user["id"], status="active")
    db.add(mat)
    db.commit()
    db.refresh(mat)
    await write_audit_log(
        action="training_material_create",
        user_id=current_user["id"],
        resource_type="training_material",
        resource_id=str(mat.id),
        after_value={"title": mat.title, "material_type": mat.material_type},
        request_id=get_request_id() or None,
    )
    return success(mat.to_dict())


@router.get("")
async def list_materials(
    page: int = 1,
    page_size: int = 20,
    material_type: Optional[str] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """培训材料列表（登录用户可读；archived 不展示）"""
    if material_type and material_type not in VALID_TYPES:
        raise ParamError("material_type 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(TrainingMaterial).filter(TrainingMaterial.status == "active")
    if material_type:
        query = query.filter(TrainingMaterial.material_type == material_type)
    if keyword:
        query = query.filter(TrainingMaterial.title.ilike(f"%{keyword}%"))
    total = query.count()
    rows = query.order_by(TrainingMaterial.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([m.to_dict() for m in rows], total, p.page, p.page_size))


@router.get("/{material_id}")
async def get_material(
    material_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mat = db.query(TrainingMaterial).filter(TrainingMaterial.id == material_id).first()
    if not mat or mat.status != "active":
        raise BusinessError("培训材料不存在", code=4001)
    return success(mat.to_dict())


@router.put("/{material_id}")
async def update_material(
    material_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*MATERIAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    mat = db.query(TrainingMaterial).filter(TrainingMaterial.id == material_id).first()
    if not mat or mat.status != "active":
        raise BusinessError("培训材料不存在", code=4001)
    data = _validate_payload(payload)
    before = {"title": mat.title, "content": mat.content, "material_type": mat.material_type}
    mat.title = data["title"]
    mat.content = data["content"]
    mat.material_type = data["material_type"]
    db.commit()
    db.refresh(mat)
    await write_audit_log(
        action="training_material_update",
        user_id=current_user["id"],
        resource_type="training_material",
        resource_id=str(mat.id),
        before_value=before,
        after_value={"title": mat.title, "material_type": mat.material_type},
        request_id=get_request_id() or None,
    )
    return success(mat.to_dict())


@router.delete("/{material_id}")
async def archive_material(
    material_id: int,
    current_user: dict = Depends(require_roles(*MATERIAL_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    mat = db.query(TrainingMaterial).filter(TrainingMaterial.id == material_id).first()
    if not mat or mat.status != "active":
        raise BusinessError("培训材料不存在", code=4001)
    mat.status = "archived"
    db.commit()
    db.refresh(mat)
    await write_audit_log(
        action="training_material_archive",
        user_id=current_user["id"],
        resource_type="training_material",
        resource_id=str(mat.id),
        request_id=get_request_id() or None,
    )
    return success(mat.to_dict())
