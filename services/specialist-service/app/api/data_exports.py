"""数据导出审批（三期 K，需求 3.8(3)）：敏感数据导出须经合规部审批。
一期导出物仅 conversations 对话明细；SLA=3 自然日（仅高亮提醒，不自动放行）。"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, success
from shared.common.xlsx import sanitize_cell as _sanitize_cell
from shared.models.user import User

from app.models.conversation import Conversation
from app.models.export_request import ExportRequest
from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/data-exports", tags=["data-exports"])

EXPORT_ROLES = ("admin", "manager", "compliance")
VALID_EXPORT_TYPES = ("conversations",)
SLA_DAYS = 3
DOWNLOAD_EXPIRE_DAYS = 7
ROW_CAP = 50000


def _build_conversations_xlsx(request_id: int, rows: list, out_dir: str = os.path.join("logs", "exports")) -> str:
    """把对话明细行写入 xlsx，返回文件路径。rows 为 dict 列表（已脱敏/受限字段）。"""
    from openpyxl import Workbook
    os.makedirs(out_dir, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "对话明细"
    ws.append(["id", "user_id", "specialist_id", "session_id", "role", "content", "blocked", "created_at"])
    for r in rows:
        ws.append([
            _sanitize_cell(r.get("id")), _sanitize_cell(r.get("user_id")),
            _sanitize_cell(r.get("specialist_id")), _sanitize_cell(r.get("session_id")),
            _sanitize_cell(r.get("role")), _sanitize_cell(r.get("content")),
            _sanitize_cell(r.get("blocked")), _sanitize_cell(r.get("created_at")),
        ])
    path = os.path.join(out_dir, f"export_{request_id}.xlsx")
    wb.save(path)
    return path


@router.post("/requests")
async def create_export_request(
    payload: dict,
    current_user: dict = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    """申请人 admin/manager：提交敏感数据导出申请 → pending。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    export_type = payload.get("export_type") or "conversations"
    if export_type not in VALID_EXPORT_TYPES:
        raise ParamError("export_type 不合法（一期仅 conversations）")
    reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    if not reason:
        raise ParamError("导出目的必填")
    if len(reason) > 500:
        raise ParamError("原因长度不能超过 500 字符")
    req = ExportRequest(requester_id=current_user["id"], export_type=export_type, reason=reason, status="pending")
    db.add(req)
    db.commit()
    db.refresh(req)
    await write_audit_log(
        action="export_request_create", user_id=current_user["id"],
        resource_type="export_request", resource_id=str(req.id),
        after_value={"export_type": export_type, "reason": reason},
        request_id=get_request_id() or None,
    )
    return success(req.to_dict())


@router.get("/requests")
async def list_export_requests(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    current_user: dict = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
):
    """审批人列表：分页 + status 过滤 + SLA 超时（pending 且 created_at+3 天 < now）高亮。"""
    if status and status not in ("pending", "approved", "rejected"):
        raise ParamError("status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(ExportRequest).outerjoin(User, ExportRequest.requester_id == User.id)
    if status:
        q = q.filter(ExportRequest.status == status)
    total = q.count()
    rows = (
        q.order_by(ExportRequest.id.desc())
        .offset(p.offset).limit(p.limit)
        .with_entities(ExportRequest, User.full_name)
        .all()
    )
    now = datetime.utcnow()
    items = []
    for req, requester_name in rows:
        d = req.to_dict()
        d["requester_name"] = requester_name
        d["sla_overdue"] = bool(
            req.status == "pending"
            and req.created_at
            and req.created_at + timedelta(days=SLA_DAYS) < now
        )
        items.append(d)
    return success(paginate(items, total, p.page, p.page_size))


@router.post("/requests/{request_id}/review")
async def review_export_request(
    request_id: int,
    payload: dict,
    # M-2（2026-08-24 审查修复）：审批收敛到 compliance/admin。申请人角色是
    # admin/manager —— manager 既可申请又可审批 = 自审自批；admin 保留兜底
    # 但被下方自批守卫拦住。列表查看仍开放 EXPORT_ROLES（申请人需看进度）。
    current_user: dict = Depends(require_roles("compliance", "admin")),
    db: Session = Depends(get_db),
):
    """合规部审批：approve → 生成对话明细 xlsx + expires_at；reject 必填 reason。"""
    req = db.query(ExportRequest).filter(ExportRequest.id == request_id).first()
    if not req:
        raise BusinessError("导出申请不存在", code=4001)
    if req.status != "pending":
        raise BusinessError("当前状态不可审批（仅待审批可审）", code=4001)
    # M-2：本人申请本人批 = 自审自批，一律拒绝（含 admin）
    if req.requester_id == current_user["id"]:
        raise BusinessError("不能审批自己提交的导出申请", code=4001)
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
    if verdict == "approve":
        rows = [
            {
                "id": c.id, "user_id": c.user_id, "specialist_id": c.specialist_id,
                "session_id": c.session_id, "role": c.role, "content": c.content,
                "blocked": bool((c.compliance_result or {}).get("blocked")) if c.compliance_result else False,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in db.query(Conversation).order_by(Conversation.id).limit(ROW_CAP).all()
        ]
        path = await asyncio.to_thread(_build_conversations_xlsx, req.id, rows)
        req.file_url = path
        req.expires_at = datetime.utcnow() + timedelta(days=DOWNLOAD_EXPIRE_DAYS)
    req.status = "approved" if verdict == "approve" else "rejected"
    req.approve_reason = reason if verdict == "reject" else None
    req.approver_id = current_user["id"]
    req.responded_at = datetime.utcnow()
    db.commit()
    db.refresh(req)
    await write_audit_log(
        action="export_request_review", user_id=current_user["id"],
        resource_type="export_request", resource_id=str(req.id),
        after_value={"status": req.status, "approve_reason": req.approve_reason},
        request_id=get_request_id() or None,
    )
    return success(req.to_dict())


@router.get("/requests/{request_id}/download")
async def download_export(
    request_id: int,
    current_user: dict = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
):
    """审批通过后下载对话明细 xlsx（expires_at 未过期）。"""
    req = db.query(ExportRequest).filter(ExportRequest.id == request_id).first()
    if not req or req.status != "approved":
        raise BusinessError("导出申请不存在或未通过审批", code=4001)
    if req.expires_at and req.expires_at < datetime.utcnow():
        raise BusinessError("导出文件已过期，请重新申请", code=4001)
    if not req.file_url or not os.path.exists(req.file_url):
        raise BusinessError("导出文件不存在", code=4001)
    return FileResponse(req.file_url, filename=f"conversations_export_{req.id}.xlsx")
