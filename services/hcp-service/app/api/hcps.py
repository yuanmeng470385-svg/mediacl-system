"""医生/专家管理服务 API 路由"""
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from shared.common.response import success, ParamError, BusinessError
from shared.common.auth import get_current_user, require_roles
from shared.common.internal_auth import require_internal_key

# 医生库维护端点（S6 RBAC）：写操作限 admin/manager
HCP_ADMIN_ROLES = ("admin", "manager")
# M-3（2026-08-24 审查修复）：档案读取角色。列表/详情/画像含手机号、邮箱等
# 医生 PII，此前任意登录角色（doctor/finance 等）都能拉全量档案 —— 收敛到
# 实际使用方：admin/manager（web 医生管理）+ rep（mobile 拜访/画像）。
# 医生端 app 不调 /hcps；标签端点仍开放（B5：协作元数据非敏感字段）。
HCP_READ_ROLES = ("admin", "manager", "rep")
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from app.models.hcp import Hcp
from app.db.repositories.hcp_repo import HcpRepo, HCP_WRITABLE_FIELDS
from app.db.repositories.visit_interaction_repo import list_interactions
from app.services.excel_parser import parse_hcp_excel
from app.services.profile_generator import ProfileGenerator
from app.services.audit_client import write_audit_log
from app.core.hcp_cache import cache as hcp_cache

router = APIRouter(prefix="/api/v1/hcps", tags=["hcps"])
logger = logging.getLogger(__name__)

# M13（2026-08-21 审计）：批量导入文件大小上限 —— 防超大文件/zip 压缩炸弹占内存
MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024


def _get_hcp_or_404(db: Session, hcp_id: int) -> Hcp:
    # E4（2026-08-13）：裸 HTTPException(detail="医生档案不存在") → BusinessError
    # code 4001（业务错误区间）。经 Wave 1 共享处理器渲染为统一形状
    # {code:4001, message, data}（HTTP 422），语义 code 比按 status 映射的
    # 4000 更准确（函数名保留，避免改散全部调用点与测试注入）。
    hcp = HcpRepo.get(db, hcp_id)
    if not hcp:
        raise BusinessError("医生档案不存在", code=4001)
    return hcp


def _parse_hcp_id(hcp_id) -> int:
    """路径参数 hcp_id 显式整数校验（E4，2026-08-13）。

    路由声明 hcp_id: str，非法值（非数字串）在这里抛 ParamError（400，
    code 1000 统一形状），替代 FastAPI 默认 422 —— 形状/语义与本服务其余
    参数错误一致。
    """
    try:
        return int(hcp_id)
    except (TypeError, ValueError):
        raise ParamError("hcp_id 必须为整数")


async def _invalidate_hcp_cache(hcp_id: int) -> None:
    """写路径失效：档案与画像缓存一起清（画像依赖档案字段）。

    Redis delete/scan_iter 是同步阻塞调用，统一 to_thread 下线程池执行，
    不占事件循环（2026-08-21 审计：4 个写端点同步清缓存阻塞 loop）。
    """
    await asyncio.to_thread(hcp_cache.invalidate, f"hcp:{hcp_id}")
    await asyncio.to_thread(hcp_cache.invalidate_profile, hcp_id)


def _validate_hcp_fields(request: dict) -> dict:
    """白名单校验（防 mass assignment，与 specialist-service 契约一致）。

    只接受 HCP_WRITABLE_FIELDS 字段；id/created_at/updated_at 等系统字段
    与未知 key 一律 400 —— 否则客户端可借此覆盖主键/时间戳/任意列。
    """
    # E5（2026-08-13）：请求体非 dict（防御 FastAPI 校验之外的直调/签名漂移）
    # → ParamError，而非 .keys() AttributeError 冒泡成 500
    if not isinstance(request, dict):
        raise ParamError("请求体必须为 JSON 对象")
    extra = set(request.keys()) - HCP_WRITABLE_FIELDS
    if extra:
        raise ParamError(f"不允许的字段: {sorted(extra)}")
    return request


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
    current_user: dict = Depends(require_roles(*HCP_READ_ROLES)),
    db: Session = Depends(get_db),
):
    """医生列表（分页 + 筛选：姓名/医院/科室/职称/区域/状态/标签）。

    M-3：读取收敛到 HCP_READ_ROLES（admin/manager/rep），档案含医生 PII。"""
    p = PaginationParams(page=page, page_size=page_size)
    items, total = HcpRepo.list(
        db, page=p.page, page_size=p.page_size,
        name=name, hospital=hospital, department=department,
        title=title, region=region, status=status, tag=tag,
    )
    return success(paginate([i.to_dict() for i in items], total, p.page, p.page_size))


@router.get("/{hcp_id}")
async def get_hcp(
    hcp_id: str,
    current_user: dict = Depends(require_roles(*HCP_READ_ROLES)),
    db: Session = Depends(get_db),
):
    """医生详情（Redis 缓存：hcp:{id}，TTL 300s；写路径即时失效，见 _invalidate_hcp_cache）。

    M-3：读取收敛到 HCP_READ_ROLES（admin/manager/rep）。"""
    hcp_id = _parse_hcp_id(hcp_id)
    cached = hcp_cache.get(f"hcp:{hcp_id}")
    if cached is not None:
        return success(cached)
    data = _get_hcp_or_404(db, hcp_id).to_dict()
    hcp_cache.set(f"hcp:{hcp_id}", data)
    return success(data)


# ==================== 画像 & 互动历史 ====================

@router.get("/{hcp_id}/profile")
async def get_hcp_profile(
    hcp_id: str,
    current_user: dict = Depends(require_roles(*HCP_READ_ROLES)),
    db: Session = Depends(get_db),
):
    """医生画像（聚合互动历史 + AI 生成，LLM 不可用时降级为基础数据）。

    M-3（2026-08-24 审查修复）：与列表/详情同口径收敛到 HCP_READ_ROLES ——
    画像响应含 hcp.to_dict()（手机号/邮箱 PII），此前任意登录角色可拉。

    H3（2026-08-11）：互动历史按查看者过滤——admin/manager 聚合全部代表的互动，
    rep 只聚合本人（画像含 ai_summary/异议/兴趣等敏感内容，此前任意登录用户可
    拉取全部代表与该医生的互动细节）。缓存按查看者分键（profile:{id}:all /
    profile:{id}:u{uid}），避免不同视角内容串用户。
    """
    hcp_id = _parse_hcp_id(hcp_id)
    view_all = current_user.get("role") in ("admin", "manager")
    viewer_key = "all" if view_all else f"u{current_user['id']}"
    cache_key = f"profile:{hcp_id}:{viewer_key}"

    cached = hcp_cache.get(cache_key)
    if cached is not None:
        return success(cached)

    hcp = _get_hcp_or_404(db, hcp_id)
    generator = ProfileGenerator()
    # LLM 调用是同步阻塞（OpenAI SDK）——丢线程池执行，防事件循环被占：
    # 真机实测画像生成 ~8s 期间 hcp-service 其他请求（/hcps/{id}、/interactions）
    # 全部排队 7.7s（同一时间网关同时发来三请求，只有 LLM 结束才一起返回）
    result = await asyncio.to_thread(
        lambda: generator.generate(db, hcp, user_id=None if view_all else current_user["id"])
    )
    result["hcp"] = hcp.to_dict()
    hcp_cache.set(cache_key, result)

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
    hcp_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """互动历史（读 visit-service 的拜访记录）。

    S7 权限：admin/manager 可见全部代表的记录；其他角色（rep 等）只能看到
    自己的记录 —— 与 visit 侧 S4 规则一致，防跨用户泄漏他人拜访总结。
    """
    hcp_id = _parse_hcp_id(hcp_id)
    _get_hcp_or_404(db, hcp_id)
    if current_user.get("role") in HCP_ADMIN_ROLES:
        user_id = None  # 管理角色：不过滤
    else:
        user_id = current_user.get("id")
    # 契约：返回裸数组（web/mobile 两端均按数组解包，勿再包 {items: ...}）
    return success(list_interactions(db, hcp_id, user_id=user_id))


# ==================== 新增 & 编辑 ====================

@router.post("")
async def create_hcp(
    request: dict,
    current_user: dict = Depends(require_roles(*HCP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """新增医生档案（仅白名单字段）"""
    data = _validate_hcp_fields(request)
    name = (data.get("name") or "").strip()
    if not name:
        raise ParamError("name 不能为空")
    hcp = HcpRepo.create(db, data)
    # E7（2026-08-13）：写操作留痕（与 profile-update 同口径，失败不影响业务）
    await write_audit_log(
        user_id=current_user["id"],
        action="hcp_create",
        resource_type="hcp",
        resource_id=str(hcp.id),
        after_value=data,
    )
    return success(hcp.to_dict(), "医生档案已创建")


@router.put("/{hcp_id}")
async def update_hcp(
    hcp_id: str,
    request: dict,
    current_user: dict = Depends(require_roles(*HCP_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """编辑医生档案（仅白名单字段）"""
    hcp_id = _parse_hcp_id(hcp_id)
    data = _validate_hcp_fields(request)
    hcp = _get_hcp_or_404(db, hcp_id)
    before = hcp.to_dict()
    if "name" in data and not (data.get("name") or "").strip():
        raise ParamError("name 不能为空")
    hcp = HcpRepo.update(db, hcp, data)
    await _invalidate_hcp_cache(hcp_id)  # 档案变更：缓存即时失效
    # E7（2026-08-13）：编辑留痕（before/after，仅记白名单字段实际变更）
    await write_audit_log(
        user_id=current_user["id"],
        action="hcp_update",
        resource_type="hcp",
        resource_id=str(hcp_id),
        before_value=before,
        after_value=data,
    )
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
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise ParamError("仅支持 .xlsx/.xlsm 文件")

    # M13（2026-08-21 审计）：大小上限 —— zip 压缩炸弹/超大文件防内存放大
    file.file.seek(0, 2)  # io.SEEK_END
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_IMPORT_FILE_SIZE:
        raise ParamError(f"Excel 文件超过 {MAX_IMPORT_FILE_SIZE // (1024 * 1024)}MB 上限")

    try:
        rows = parse_hcp_excel(file.file)
    except Exception as e:
        logger.error(f"Excel 解析失败: {e}")
        raise ParamError(f"Excel 解析失败: {e}")

    if not rows:
        raise ParamError("未找到有效数据（第一行为表头，姓名必填）")

    imported, errors = HcpRepo.batch_create(db, rows)
    # E7（2026-08-13）：批量导入留痕（after 记汇总数字；单行明细由审计服务
    # 按 request_id 关联，避免响应体级大对象塞进审计 payload）
    await write_audit_log(
        user_id=current_user["id"],
        action="hcp_batch_import",
        resource_type="hcp",
        after_value={
            "total": len(rows),
            "imported": imported,
            "failed": len(errors),
        },
    )
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
    hcp_id: str,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """添加标签 {"tags": ["KOL", "学术型"]}

    B5 修复（2026-08-12）：原仅 admin/manager —— 拜访后给医生打标签是
    代表的日常工作（兴趣点落标签），放开为任意登录用户；标签是协作性元数据，
    非敏感档案字段（画像/互动详情仍受角色限制）。
    """
    hcp_id = _parse_hcp_id(hcp_id)
    if not isinstance(request, dict):
        raise ParamError("请求体必须为 JSON 对象")
    tags = request.get("tags", [])
    if not tags:
        raise ParamError("tags 不能为空")
    hcp = _get_hcp_or_404(db, hcp_id)
    before_tags = list(hcp.tags or [])
    hcp = HcpRepo.add_tags(db, hcp, tags)
    await _invalidate_hcp_cache(hcp_id)
    # E7（2026-08-13）：标签增删留痕（before/after 标签列表）
    await write_audit_log(
        user_id=current_user["id"],
        action="hcp_tags_add",
        resource_type="hcp",
        resource_id=str(hcp_id),
        before_value={"tags": before_tags},
        after_value={"tags": hcp.tags},
    )
    return success(hcp.to_dict())


@router.delete("/{hcp_id}/tags")
async def remove_hcp_tags(
    hcp_id: str,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除标签 {"tags": ["KOL"]}（与 add 同口径：任意登录用户，B5 放开）"""
    hcp_id = _parse_hcp_id(hcp_id)
    if not isinstance(request, dict):
        raise ParamError("请求体必须为 JSON 对象")
    tags = request.get("tags", [])
    if not tags:
        raise ParamError("tags 不能为空")
    hcp = _get_hcp_or_404(db, hcp_id)
    before_tags = list(hcp.tags or [])
    hcp = HcpRepo.remove_tags(db, hcp, tags)
    await _invalidate_hcp_cache(hcp_id)
    # E7（2026-08-13）：标签增删留痕（before/after 标签列表）
    await write_audit_log(
        user_id=current_user["id"],
        action="hcp_tags_remove",
        resource_type="hcp",
        resource_id=str(hcp_id),
        before_value={"tags": before_tags},
        after_value={"tags": hcp.tags},
    )
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
    # E5（2026-08-13）：请求体非 dict → ParamError（防 .get() AttributeError 冒泡 500）
    if not isinstance(request, dict):
        raise ParamError("请求体必须为 JSON 对象")
    hcp_id = request.get("hcp_id")
    # E4（2026-08-13）：hcp_id 显式正整数校验（bool 是 int 子类，单独排除）
    if isinstance(hcp_id, bool) or not isinstance(hcp_id, int) or hcp_id <= 0:
        raise ParamError("hcp_id 必须为正整数")
    hcp = HcpRepo.get(db, hcp_id)
    if not hcp:
        # E4：裸 HTTPException 404 → BusinessError code 4001（统一形状 + 业务语义码）
        raise BusinessError("医生档案不存在", code=4001)
    updates = {
        "academic_background": request.get("academic_background"),
        "prescription_preference": request.get("prescription_preference"),
        "influence_level": request.get("influence_level"),
        "tags": request.get("tags"),
    }
    hcp = HcpRepo.merge_profile(db, hcp, updates)
    await _invalidate_hcp_cache(hcp_id)  # 画像更新（拜访结束）：档案+画像缓存即时失效
    await write_audit_log(
        user_id=None, action="hcp_profile_update_from_visit",
        resource_type="hcp", resource_id=str(hcp_id),
        after_value={"source": request.get("source"), "visit_id": request.get("visit_id"),
                     "updated": [k for k, v in updates.items() if v]},
    )
    return success(hcp.to_dict())
