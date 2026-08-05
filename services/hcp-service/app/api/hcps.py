"""医生/专家管理服务 API 路由"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from shared.common.response import success, ParamError
from shared.common.auth import get_current_user, require_roles
from shared.common.internal_auth import require_internal_key

# 医生库维护端点（S6 RBAC）：写操作限 admin/manager
HCP_ADMIN_ROLES = ("admin", "manager")
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from app.models.hcp import Hcp
from app.db.repositories.hcp_repo import HcpRepo
from app.db.repositories.visit_interaction_repo import list_interactions
from app.services.excel_parser import parse_hcp_excel
from app.services.profile_generator import ProfileGenerator
from app.services.audit_client import write_audit_log

router = APIRouter(prefix="/api/v1/hcps", tags=["hcps"])
logger = logging.getLogger(__name__)


def _get_hcp_or_404(db: Session, hcp_id: int) -> Hcp:
    hcp = HcpRepo.get(db, hcp_id)
    if not hcp:
        raise HTTPException(status_code=404, detail="医生档案不存在")
    return hcp


# ==================== 列表 & 详情 ====================

@router.get("")
async def list_hcps(
    page: int = 1,
    page_size: int = 20,
    name: Optional[str] = None,
    hospital: Optional[str] = None,
    department: Optional[str] = None,
    title: Optional[str] = None,
    region: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """医生列表（分页 + 筛选：姓名/医院/科室/职称/区域/状态/标签）"""
    p = PaginationParams(page=page, page_size=page_size)
    items, total = HcpRepo.list(
        db, page=p.page, page_size=p.page_size,
        name=name, hospital=hospital, department=department,
        title=title, region=region, status=status, tag=tag,
    )
    return success(paginate([i.to_dict() for i in items], total, p.page, p.page_size))


@router.get("/{hcp_id}")
async def get_hcp(
    hcp_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """医生详情"""
    return success(_get_hcp_or_404(db, hcp_id).to_dict())


# ==================== 画像 & 互动历史 ====================

@router.get("/{hcp_id}/profile")
async def get_hcp_profile(
    hcp_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """医生画像（聚合互动历史 + AI 生成，LLM 不可用时降级为基础数据）"""
    hcp = _get_hcp_or_404(db, hcp_id)
    generator = ProfileGenerator()
    result = generator.generate(db, hcp)
    result["hcp"] = hcp.to_dict()

    # AI 行为留痕（仅实际使用了 AI 时）
    if not result.get("degraded"):
        await write_audit_log(
            user_id=current_user["id"],
            action="hcp_profile_generate",
            resource_type="hcp",
            resource_id=str(hcp_id),
            ai_involved=True,
            ai_model="qwen-max",
            ai_response=str(result.get("ai_profile"))[:2000],
        )
    return success(result)


@router.get("/{hcp_id}/interactions")
async def get_hcp_interactions(
    hcp_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """互动历史（读 visit-service 的拜访记录）"""
    _get_hcp_or_404(db, hcp_id)
    return success({"items": list_interactions(db, hcp_id)})


# ==================== 新增 & 编辑 ====================

@router.post("")
async def create_hcp(
    request: dict,
    current_user: dict = Depends(require_roles(*HCP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """新增医生档案"""
    name = (request.get("name") or "").strip()
    if not name:
        raise ParamError("name 不能为空")
    hcp = HcpRepo.create(db, request)
    return success(hcp.to_dict(), "医生档案已创建")


@router.put("/{hcp_id}")
async def update_hcp(
    hcp_id: int,
    request: dict,
    current_user: dict = Depends(require_roles(*HCP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """编辑医生档案（仅更新传入字段）"""
    hcp = _get_hcp_or_404(db, hcp_id)
    if "name" in request and not (request.get("name") or "").strip():
        raise ParamError("name 不能为空")
    hcp = HcpRepo.update(db, hcp, request)
    return success(hcp.to_dict())


# ==================== 批量导入 ====================

@router.post("/batch-import")
async def batch_import_hcps(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_roles(*HCP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Excel 批量导入医生档案

    表头：姓名(必填) | 医院 | 科室 | 职称 | 专业 | 电话 | 邮箱 | 区域 | 影响力 | 标签
    """
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise ParamError("仅支持 .xlsx 文件")

    try:
        rows = parse_hcp_excel(file.file)
    except Exception as e:
        logger.error(f"Excel 解析失败: {e}")
        raise ParamError(f"Excel 解析失败: {e}")

    if not rows:
        raise ParamError("未找到有效数据（第一行为表头，姓名必填）")

    imported, errors = HcpRepo.batch_create(db, rows)
    return success(
        {
            "total": len(rows),
            "imported": imported,
            "failed": len(errors),
            "errors": errors[:20],  # 只回传前 20 条错误，避免响应过大
        },
        f"导入完成：成功 {imported} 条，失败 {len(errors)} 条",
    )


# ==================== 标签管理 ====================

@router.post("/{hcp_id}/tags")
async def add_hcp_tags(
    hcp_id: int,
    request: dict,
    current_user: dict = Depends(require_roles(*HCP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """添加标签 {"tags": ["KOL", "学术型"]}"""
    tags = request.get("tags", [])
    if not tags:
        raise ParamError("tags 不能为空")
    hcp = _get_hcp_or_404(db, hcp_id)
    hcp = HcpRepo.add_tags(db, hcp, tags)
    return success(hcp.to_dict())


@router.delete("/{hcp_id}/tags")
async def remove_hcp_tags(
    hcp_id: int,
    request: dict,
    current_user: dict = Depends(require_roles(*HCP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """删除标签 {"tags": ["KOL"]}"""
    tags = request.get("tags", [])
    if not tags:
        raise ParamError("tags 不能为空")
    hcp = _get_hcp_or_404(db, hcp_id)
    hcp = HcpRepo.remove_tags(db, hcp, tags)
    return success(hcp.to_dict())


# ==================== 内部接口（visit-service 拜访后画像更新） ====================

@router.post("/profile-update")
async def update_hcp_profile_from_visit(
    request: dict,
    db: Session = Depends(get_db),
    _internal: bool = Depends(require_internal_key),
):
    """拜访后画像更新（内部接口，visit-service 调用）：
    {hcp_id, academic_background?, prescription_preference?, influence_level?, tags?, source, visit_id?}
    """
    hcp_id = request.get("hcp_id")
    if not hcp_id:
        raise ParamError("hcp_id 不能为空")
    hcp = HcpRepo.get(db, hcp_id)
    if not hcp:
        raise HTTPException(status_code=404, detail="医生档案不存在")
    updates = {
        "academic_background": request.get("academic_background"),
        "prescription_preference": request.get("prescription_preference"),
        "influence_level": request.get("influence_level"),
        "tags": request.get("tags"),
    }
    hcp = HcpRepo.merge_profile(db, hcp, updates)
    await write_audit_log(
        user_id=None, action="hcp_profile_update_from_visit",
        resource_type="hcp", resource_id=str(hcp_id),
        after_value={"source": request.get("source"), "visit_id": request.get("visit_id"),
                     "updated": [k for k, v in updates.items() if v]},
    )
    return success(hcp.to_dict())
