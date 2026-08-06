"""审计服务 API 路由"""
import logging
from typing import Optional
from datetime import datetime, timedelta
from io import BytesIO

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc, desc
import openpyxl

from shared.common.response import success, ParamError
from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.internal_auth import require_internal_key
from shared.common.pagination import paginate
from shared.models.audit_log import AuditLog

from app.core.logger import get_audit_logger

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
logger = logging.getLogger(__name__)

audit_logger = get_audit_logger()

# 审计数据查看/导出角色：审计日志含全量用户操作记录，仅管理者与合规专员可见（rep 等不开放）
AUDIT_VIEW_ROLES = ("admin", "manager", "compliance")


# ==================== 写入审计日志（内部接口） ====================

@router.post("/log")
async def write_log(
    request: dict,
    db: Session = Depends(get_db),
    _internal: bool = Depends(require_internal_key),
):
    """
    写入审计日志 — 所有微服务内部调用

    Request:
        {
            "service_name": "specialist-service",
            "user_id": 1,
            "action": "chat_response",
            "resource_type": "conversation",
            "resource_id": "123",
            "ai_involved": true,
            "ai_model": "qwen-max",
            "ai_prompt": "...",
            "ai_response": "...",
            "compliance_result": {...},
            "request_id": "uuid"
        }
    """
    log_id = audit_logger.log(db, **request)
    if log_id:
        return success({"id": log_id})
    return success(None, "日志已记录")


# ==================== 审计日志查询 ====================

@router.get("/logs")
async def search_logs(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(*AUDIT_VIEW_ROLES)),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    service_name: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None, description="开始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
):
    """
    审计日志高级搜索

    支持按时间、用户、服务、操作类型、风险等级筛选
    """
    query = db.query(AuditLog)

    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if service_name:
        query = query.filter(AuditLog.service_name == service_name)
    if action:
        query = query.filter(AuditLog.action == action)
    if risk_level:
        query = query.filter(AuditLog.risk_level == risk_level)
    if start_time:
        query = query.filter(AuditLog.timestamp >= start_time)
    if end_time:
        query = query.filter(AuditLog.timestamp <= end_time)

    total = query.count()
    items = query.order_by(desc(AuditLog.timestamp)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return success(paginate(
        [_log_to_dict(log) for log in items],
        total=total, page=page, page_size=page_size
    ))


@router.get("/logs/{log_id}")
async def get_log_detail(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(*AUDIT_VIEW_ROLES)),
):
    """查看单条日志详情"""
    log_entry = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not log_entry:
        raise ParamError("日志不存在")
    return success(_log_to_dict(log_entry))


# ==================== 监管报告导出 ====================

@router.post("/export")
async def export_report(
    request: dict,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(*AUDIT_VIEW_ROLES)),
):
    """
    导出审计报告（Excel 格式）

    Request:
        {
            "start_time": "2026-07-01T00:00:00",
            "end_time": "2026-07-31T23:59:59",
            "service_name": "specialist-service",   // 可选
            "risk_level": "high"                     // 可选
        }
    """
    query = db.query(AuditLog)

    start_time = request.get("start_time")
    end_time = request.get("end_time")
    service_name = request.get("service_name")
    risk_level = request.get("risk_level")

    if start_time:
        query = query.filter(AuditLog.timestamp >= start_time)
    if end_time:
        query = query.filter(AuditLog.timestamp <= end_time)
    if service_name:
        query = query.filter(AuditLog.service_name == service_name)
    if risk_level:
        query = query.filter(AuditLog.risk_level == risk_level)

    logs = query.order_by(desc(AuditLog.timestamp)).limit(10000).all()

    # 生成 Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "审计日志"

    # 表头
    headers = ["时间", "服务", "用户ID", "操作", "资源类型", "资源ID",
               "AI参与", "AI模型", "风险等级", "请求ID"]
    ws.append(headers)

    # 数据
    for log in logs:
        ws.append([
            log.timestamp.isoformat() if log.timestamp else "",
            log.service_name or "",
            log.user_id or "",
            log.action or "",
            log.resource_type or "",
            log.resource_id or "",
            "是" if log.ai_involved else "否",
            log.ai_model or "",
            log.risk_level or "",
            log.request_id or "",
        ])

    # 调整列宽
    for col in ws.columns:
        max_length = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    # 导出行为本身入审计（直接写本服务审计引擎，非 HTTP 调用，无角色/递归问题）
    audit_logger.log(
        db,
        service_name="audit-service",
        user_id=current_user["id"],
        action="audit_report_export",
        resource_type="audit_report",
        after_value={
            "start_time": request.get("start_time"),
            "end_time": request.get("end_time"),
            "service_name": request.get("service_name"),
            "risk_level": request.get("risk_level"),
            "rows": len(logs),
        },
        client_ip=_client_ip(http_request),
    )

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==================== 审计统计 ====================

@router.get("/stats")
async def audit_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_roles(*AUDIT_VIEW_ROLES)),
    days: int = Query(30, description="统计最近 N 天"),
):
    """审计统计数据"""
    since = datetime.utcnow() - timedelta(days=days)

    total = db.query(sqlfunc.count(AuditLog.id)).scalar()
    recent = db.query(sqlfunc.count(AuditLog.id)).filter(
        AuditLog.timestamp >= since
    ).scalar()

    # 按风险等级分布
    risk_dist = (
        db.query(AuditLog.risk_level, sqlfunc.count(AuditLog.id))
        .filter(AuditLog.timestamp >= since)
        .group_by(AuditLog.risk_level)
        .all()
    )

    # 按服务分布
    service_dist = (
        db.query(AuditLog.service_name, sqlfunc.count(AuditLog.id))
        .filter(AuditLog.timestamp >= since)
        .group_by(AuditLog.service_name)
        .all()
    )

    # 按日趋势（最近 N 天按日期分组，供仪表盘趋势图）
    day_rows = (
        db.query(sqlfunc.date(AuditLog.timestamp).label("day"), sqlfunc.count(AuditLog.id))
        .filter(AuditLog.timestamp >= since)
        .group_by(sqlfunc.date(AuditLog.timestamp))
        .order_by(sqlfunc.date(AuditLog.timestamp))
        .all()
    )
    trend_daily = [{"date": str(day), "count": cnt} for day, cnt in day_rows]

    return success({
        "total_records": total,
        "recent_records": recent,
        "recent_days": days,
        "risk_distribution": {k or "unknown": v for k, v in risk_dist},
        "service_distribution": {k or "unknown": v for k, v in service_dist},
        "trend_daily": trend_daily,
    })


# ==================== 辅助 ====================

def _client_ip(request: Request) -> Optional[str]:
    """取真实来源 IP。网关转发时以 X-Forwarded-For 首段为准。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _log_to_dict(log: AuditLog) -> dict:
    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "service_name": log.service_name,
        "user_id": log.user_id,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "ai_involved": log.ai_involved,
        "ai_model": log.ai_model,
        "ai_prompt_hash": log.ai_prompt_hash,
        "ai_response_hash": log.ai_response_hash,
        "risk_level": log.risk_level,
        "client_ip": log.client_ip,
        "request_id": log.request_id,
    }
