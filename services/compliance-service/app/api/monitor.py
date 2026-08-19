"""合规监控（二期 E，需求 3.2(3)(4)）：聚合日报 / 违规趋势 / 待复核名单。
拦截聚合基于 compliance_blocks（同库直连 users 取代表姓名，与 blocks/stats 同口径）。
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import ParamError, success
from shared.models.compliance import ComplianceBlock
from shared.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance-monitor"])

MONITOR_ADMIN_ROLES = ("admin", "manager", "compliance")

# 待复核阈值（需求 3.2(3)：24 小时内拦截 ≥5 次标记待复核，可配置）
REVIEW_THRESHOLD = int(os.getenv("REVIEW_BLOCK_THRESHOLD", "5"))
REVIEW_WINDOW_HOURS = int(os.getenv("REVIEW_WINDOW_HOURS", "24"))


@router.get("/daily-summary")
async def daily_summary(
    days: int = Query(7, ge=1, le=90),
    _admin: dict = Depends(require_roles(*MONITOR_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """拦截聚合日报：按天 × 按规则 × 按 action 聚合（风控看板数据源）。

    拦截口径 = action='reject'；warn/log 不在拦截计数内。
    """
    since = datetime.utcnow() - timedelta(days=days)
    base = (
        db.query(ComplianceBlock)
        .filter(ComplianceBlock.blocked_at >= since)
        .filter(ComplianceBlock.action == "reject")
    )

    by_rule_rows = (
        base.with_entities(
            ComplianceBlock.rule_code, sqlfunc.count(ComplianceBlock.id)
        ).group_by(ComplianceBlock.rule_code).all()
    )
    by_action_rows = (
        base.with_entities(
            ComplianceBlock.action, sqlfunc.count(ComplianceBlock.id)
        ).group_by(ComplianceBlock.action).all()
    )
    by_day_rows = (
        base.with_entities(
            sqlfunc.date(ComplianceBlock.blocked_at), sqlfunc.count(ComplianceBlock.id)
        ).group_by(sqlfunc.date(ComplianceBlock.blocked_at)).all()
    )
    return success({
        "total": base.count(),
        "by_rule": [{"rule_code": r, "count": c} for r, c in by_rule_rows],
        "by_action": [{"action": a, "count": c} for a, c in by_action_rows],
        "by_day": [{"date": str(d), "count": c} for d, c in by_day_rows],
        "days": days,
    })


@router.get("/trends")
async def compliance_trends(
    days: int = Query(30, ge=1, le=90),
    _admin: dict = Depends(require_roles(*MONITOR_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """违规趋势分析（需求 3.2(4)）：时间曲线 + 代表排名 + 敏感词（规则）频率。

    拦截口径 = action='reject'；warn/log 不在拦截计数内。
    """
    since = datetime.utcnow() - timedelta(days=days)

    time_rows = (
        db.query(
            sqlfunc.date(ComplianceBlock.blocked_at).label("date"),
            sqlfunc.count(ComplianceBlock.id),
        )
        .filter(ComplianceBlock.blocked_at >= since)
        .filter(ComplianceBlock.action == "reject")
        .group_by(sqlfunc.date(ComplianceBlock.blocked_at))
        .all()
    )
    rep_rows = (
        db.query(
            User.full_name.label("rep_name"), User.id.label("user_id"),
            sqlfunc.count(ComplianceBlock.id),
        )
        .outerjoin(User, ComplianceBlock.user_id == User.id)
        .filter(ComplianceBlock.blocked_at >= since)
        .filter(ComplianceBlock.action == "reject")
        .group_by(User.id, User.full_name)
        .order_by(sqlfunc.count(ComplianceBlock.id).desc())
        .limit(10)
        .all()
    )
    rule_rows = (
        db.query(
            ComplianceBlock.rule_code, ComplianceBlock.rule_name,
            sqlfunc.count(ComplianceBlock.id),
        )
        .filter(ComplianceBlock.blocked_at >= since)
        .filter(ComplianceBlock.action == "reject")
        .group_by(ComplianceBlock.rule_code, ComplianceBlock.rule_name)
        .order_by(sqlfunc.count(ComplianceBlock.id).desc())
        .all()
    )
    return success({
        "time_series": [{"date": str(d), "count": c} for d, c in time_rows],
        "rep_ranking": [{"user_id": uid, "rep_name": name or "未知", "count": c} for name, uid, c in rep_rows],
        "rule_frequency": [{"rule_code": rc, "rule_name": rn or rc, "count": c} for rc, rn, c in rule_rows],
    })


@router.get("/review-queue")
async def review_queue(
    _admin: dict = Depends(require_roles(*MONITOR_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """待复核名单：同一代表（user）近窗口内拦截计数超阈值 → 标记待复核（不做自动冻结）"""
    since = datetime.utcnow() - timedelta(hours=REVIEW_WINDOW_HOURS)
    rows = (
        db.query(
            ComplianceBlock.user_id, User.full_name, User.phone,
            sqlfunc.count(ComplianceBlock.id).label("block_count"),
        )
        .outerjoin(User, ComplianceBlock.user_id == User.id)
        .filter(ComplianceBlock.blocked_at >= since)
        .group_by(ComplianceBlock.user_id, User.full_name, User.phone)
        .having(sqlfunc.count(ComplianceBlock.id) >= REVIEW_THRESHOLD)
        .order_by(sqlfunc.count(ComplianceBlock.id).desc())
        .all()
    )
    items = [{
        "user_id": uid, "rep_name": name or "未知", "rep_phone": phone or "",
        "block_count": cnt, "window_hours": REVIEW_WINDOW_HOURS,
        "threshold": REVIEW_THRESHOLD,
    } for uid, name, phone, cnt in rows]
    return success({"items": items, "threshold": REVIEW_THRESHOLD, "window_hours": REVIEW_WINDOW_HOURS})
