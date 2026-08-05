"""合规监管自查报告导出（xlsx）"""
import io
import logging
from datetime import datetime
from typing import List, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from shared.common.db_session import get_db
from shared.common.response import ParamError
from shared.common.auth import require_roles
from shared.models.compliance import ComplianceBlock, ComplianceRule
from app.services.audit_client import write_audit_log

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])
logger = logging.getLogger(__name__)

RULE_ADMIN_ROLES = ("admin", "manager", "compliance")


def _parse_time(value) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ParamError(f"时间格式应为 ISO 8601（YYYY-MM-DDTHH:MM:SS），收到: {value}")


def build_report_workbook(rules: List[Dict], blocks: List[Dict], summary: Dict) -> Workbook:
    """组装报告 Excel（纯函数，便于单测）"""
    wb = Workbook()
    # ---- Sheet 1: 规则快照 ----
    ws = wb.active
    ws.title = "规则快照"
    ws.append(["rule_code", "rule_name", "rule_type", "severity", "action", "enabled", "version", "hit_count"])
    for r in rules:
        ws.append([r["rule_code"], r["rule_name"], r["rule_type"], r["severity"],
                   r["action"], r["enabled"], r["version"], r["hit_count"]])
    # ---- Sheet 2: 拦截明细 ----
    ws2 = wb.create_sheet("拦截明细")
    ws2.append(["id", "user_id", "service_name", "content", "rule_code", "rule_name", "severity", "action", "blocked_at"])
    for b in blocks:
        ws2.append([b["id"], b["user_id"], b["service_name"], b["content"], b["rule_code"],
                    b["rule_name"], b["severity"], b["action"],
                    b["blocked_at"].isoformat() if b["blocked_at"] else None])
    # ---- Sheet 3: 汇总 ----
    ws3 = wb.create_sheet("汇总")
    ws3.append(["统计项", "值"])
    for rule_code, cnt in summary["by_rule"]:
        ws3.append(["命中规则", f"{rule_code}: {cnt}"])
    for svc, cnt in summary["by_service"]:
        ws3.append(["按服务", f"{svc}: {cnt}"])
    for day, cnt in summary["by_day"]:
        ws3.append(["按天", f"{day}: {cnt}"])
    for action, ratio in summary["action_ratio"].items():
        ws3.append(["动作占比", f"{action}: {ratio:.1%}"])
    return wb


@router.post("/report/export")
async def export_report(
    request: dict,
    current_user: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """导出监管自查报告：规则快照 + 拦截明细 + 汇总（Excel）"""
    start_time = _parse_time(request["start_time"]) if request.get("start_time") else None
    end_time = _parse_time(request["end_time"]) if request.get("end_time") else None
    if start_time and end_time and start_time > end_time:
        raise ParamError("start_time 不能晚于 end_time")

    from sqlalchemy import func as sqlfunc

    # 规则快照 + 命中次数
    rule_rows = db.query(ComplianceRule).all()
    hit_counts = dict(
        db.query(ComplianceBlock.rule_code, sqlfunc.count(ComplianceBlock.id))
        .group_by(ComplianceBlock.rule_code).all()
    )
    rules = [{**r.to_dict(), "hit_count": hit_counts.get(r.rule_code, 0)} for r in rule_rows]

    # 拦截明细
    bq = db.query(ComplianceBlock)
    if start_time:
        bq = bq.filter(ComplianceBlock.blocked_at >= start_time)
    if end_time:
        bq = bq.filter(ComplianceBlock.blocked_at <= end_time)
    block_rows = bq.order_by(ComplianceBlock.blocked_at.desc()).all()
    blocks = [{
        "id": b.id, "user_id": b.user_id, "service_name": b.service_name,
        "content": b.content, "rule_code": b.rule_code, "rule_name": b.rule_name,
        "severity": b.severity, "action": b.action, "blocked_at": b.blocked_at,
    } for b in block_rows]

    # 汇总（按时间范围统计）
    agg = db.query(ComplianceBlock.rule_code, sqlfunc.count(ComplianceBlock.id))
    if start_time:
        agg = agg.filter(ComplianceBlock.blocked_at >= start_time)
    if end_time:
        agg = agg.filter(ComplianceBlock.blocked_at <= end_time)
    agg_rows = agg.group_by(ComplianceBlock.rule_code).all()
    by_rule = [(rc, cnt) for rc, cnt in agg_rows]

    svc_agg = db.query(ComplianceBlock.service_name, sqlfunc.count(ComplianceBlock.id))
    if start_time:
        svc_agg = svc_agg.filter(ComplianceBlock.blocked_at >= start_time)
    if end_time:
        svc_agg = svc_agg.filter(ComplianceBlock.blocked_at <= end_time)
    by_service = [(s or "unknown", cnt) for s, cnt in svc_agg.group_by(ComplianceBlock.service_name).all()]

    from sqlalchemy import cast, Date
    day_agg = db.query(cast(ComplianceBlock.blocked_at, Date), sqlfunc.count(ComplianceBlock.id))
    if start_time:
        day_agg = day_agg.filter(ComplianceBlock.blocked_at >= start_time)
    if end_time:
        day_agg = day_agg.filter(ComplianceBlock.blocked_at <= end_time)
    by_day = [(d.isoformat(), cnt) for d, cnt in day_agg.group_by(cast(ComplianceBlock.blocked_at, Date)).all()]

    total = sum(cnt for _, cnt in by_rule) or 1
    action_ratio = {
        "reject": sum(1 for b in blocks if b["action"] == "reject") / total,
        "warn": sum(1 for b in blocks if b["action"] == "warn") / total,
        "log": sum(1 for b in blocks if b["action"] == "log") / total,
    }

    wb = build_report_workbook(rules, blocks, {"by_rule": by_rule, "by_service": by_service, "by_day": by_day, "action_ratio": action_ratio})
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)

    await write_audit_log(
        user_id=current_user["id"], action="compliance_report_export",
        resource_type="compliance_report",
        after_value={"start_time": request.get("start_time"), "end_time": request.get("end_time"), "rows": len(blocks)},
    )
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="compliance_report.xlsx"'},
    )
