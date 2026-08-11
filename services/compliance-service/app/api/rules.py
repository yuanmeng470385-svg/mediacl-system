"""合规审核服务 API 路由"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from shared.common.response import success, error, ParamError
from shared.common.auth import get_current_user, require_roles

# 合规规则管理端点（增/改/禁/重载）仅限合规相关人员 —— rep 不得改规则（S6 RBAC）
RULE_ADMIN_ROLES = ("admin", "manager", "compliance")
from shared.common.db_session import get_db
from shared.common.internal_auth import require_internal_key
from shared.common.pagination import paginate, PaginationParams
from sqlalchemy.orm import Session

from app.core.checker import get_checker
from app.services.audit_client import write_audit_log
from shared.models.compliance import ComplianceRule, ComplianceBlock

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])
logger = logging.getLogger(__name__)

checker = get_checker()


# ==================== 规则字段校验 ====================
# 审计 M29/M30：create/update 不做字段校验时，rule_type/action/severity 拼错会被
# checker 静默吞掉（规则永不生效），patterns 传字符串会被逐字符展开成单字符匹配
# （几乎全量误拦）—— 一律在入库前校验，非法值抛 ParamError(400) 中文提示。

VALID_RULE_TYPES = ("keyword", "regex", "semantic")
VALID_ACTIONS = ("reject", "warn", "log")
VALID_SEVERITIES = ("high", "medium", "low")


def _extract_patterns(data: dict):
    """提取匹配模式列表：content.patterns 优先，兼容顶层 patterns 直传"""
    content = data.get("content")
    if isinstance(content, dict) and "patterns" in content:
        return content["patterns"]
    if "patterns" in data:
        return data["patterns"]
    return None


def _validate_rule_fields(data: dict, partial: bool = False) -> None:
    """校验合规规则字段（create/update 共用），非法值抛 ParamError(400)。

    partial=False（新增）时 keyword/regex 规则必须提供非空 patterns；
    正则规则的 pattern 必须能编译通过，否则 checker 会静默剔除该条规则。
    """
    import re as _re

    rule_type = data.get("rule_type")
    if rule_type is not None:
        if not isinstance(rule_type, str) or rule_type not in VALID_RULE_TYPES:
            raise ParamError(
                f"rule_type 取值非法: {rule_type!r}，仅支持 {', '.join(VALID_RULE_TYPES)}"
            )
    elif not partial:
        rule_type = "keyword"  # 与 create 默认值保持一致

    action = data.get("action")
    if action is not None:
        if not isinstance(action, str) or action not in VALID_ACTIONS:
            raise ParamError(
                f"action 取值非法: {action!r}，仅支持 {', '.join(VALID_ACTIONS)}"
            )

    severity = data.get("severity")
    if severity is not None:
        if not isinstance(severity, str) or severity not in VALID_SEVERITIES:
            raise ParamError(
                f"severity 取值非法: {severity!r}，仅支持 {', '.join(VALID_SEVERITIES)}"
            )

    patterns = _extract_patterns(data)
    if patterns is not None:
        if not isinstance(patterns, list) or not patterns:
            raise ParamError(
                "content.patterns 必须是非空字符串数组（示例: [\"包治百病\", \"100%有效\"]）"
            )
        for p in patterns:
            if not isinstance(p, str) or not p.strip():
                raise ParamError("content.patterns 的每一项必须是非空字符串")

    if rule_type in ("keyword", "regex") and not patterns and not partial:
        raise ParamError(f"{rule_type} 类型规则必须提供非空的 content.patterns 匹配模式")

    if rule_type == "regex" and patterns:
        for p in patterns:
            try:
                _re.compile(p)
            except _re.error as exc:
                raise ParamError(f"正则规则 pattern {p!r} 编译失败: {exc}")


# ==================== 合规检查（核心接口） ====================

@router.post("/check")
async def check_content(
    request: dict,
    db: Session = Depends(get_db),
    _internal: bool = Depends(require_internal_key),
):
    """
    合规检查 — 所有微服务都调这个接口

    Request:
        {
            "content": "待检查的文本",
            "context": {"user_id": 1, "type": "user_input", "specialist_id": 1}
        }

    Response:
        {
            "code": 0,
            "data": {
                "blocked": false,
                "violations": [],
                "risk_level": "none"
            }
        }
    """
    content = request.get("content", "")
    context = request.get("context", {})

    if not content:
        raise ParamError("content 不能为空")

    result = checker.check(content, context)

    # 拦截记录入库（compliance_blocks）—— 之前无写入方，拦截记录页恒为空、拦截率无数据
    violations = result.get("violations") or []
    if violations:
        for v in violations:
            try:
                db.add(ComplianceBlock(
                    user_id=context.get("user_id"),
                    service_name=context.get("service_name") or context.get("type"),
                    content=content[:500],  # 截断防表膨胀，展示用
                    rule_code=v.get("rule_code"),
                    rule_name=v.get("rule_name"),
                    severity=v.get("severity"),
                    action=v.get("action"),
                    context=context,
                ))
            except Exception as exc:  # 拦截记录失败不影响检查结果
                logger.error(f"拦截记录入库失败: {exc}")
        try:
            db.commit()
        except Exception as exc:
            logger.error(f"拦截记录入库失败: {exc}")
            db.rollback()

    return success(result)


# ==================== 合规规则 CRUD ====================

@router.get("/rules")
async def list_rules(
    enabled: Optional[bool] = Query(None),
    rule_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """规则列表（分页、筛选）—— 含 patterns/content，仅限规则管理员"""
    query = db.query(ComplianceRule)
    if enabled is not None:
        query = query.filter(ComplianceRule.enabled == enabled)
    if rule_type:
        query = query.filter(ComplianceRule.rule_type == rule_type)

    total = query.count()
    items = query.order_by(ComplianceRule.id).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return success(paginate(
        [r.to_dict() for r in items],
        total=total,
        page=page,
        page_size=page_size
    ))


@router.get("/redlines")
async def list_redlines(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """红线速览（面向 rep/移动端）：仅返回展示字段，不暴露 patterns/content。

    移动端合规页与帮助中心展示的是"哪些红线不可触碰"，无需匹配规则细节。
    """
    query = db.query(ComplianceRule).filter(ComplianceRule.enabled == True)  # noqa: E712
    total = query.count()
    items = query.order_by(ComplianceRule.id).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return success(paginate(
        [{
            "rule_code": r.rule_code,
            "rule_name": r.rule_name,
            "rule_type": r.rule_type,
            "severity": r.severity,
            "action": r.action,
            "description": r.description,
            "enabled": r.enabled,
        } for r in items],
        total=total,
        page=page,
        page_size=page_size
    ))


@router.post("/rules")
async def create_rule(
    request: dict,
    current_user: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """新增合规规则"""
    rule_code = (request.get("rule_code") or "").strip()
    rule_name = (request.get("rule_name") or "").strip()
    if not rule_code or not rule_name:
        raise ParamError("rule_code 和 rule_name 不能为空")
    _validate_rule_fields(request, partial=False)

    content = request.get("content")
    if not isinstance(content, dict):
        content = {}
    patterns = _extract_patterns(request)
    if patterns is not None and "patterns" not in content:
        content = {**content, "patterns": patterns}

    rule = ComplianceRule(
        rule_code=rule_code,
        rule_name=rule_name,
        rule_type=request.get("rule_type") or "keyword",
        content=content,
        severity=request.get("severity", "high"),
        action=request.get("action", "reject"),
        description=request.get("description", ""),
        enabled=request["enabled"] if "enabled" in request else True,
        created_by=current_user["id"],
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    checker.reload()  # 让本 worker 立即生效（其他 worker 靠 TTL 自动重载）
    logger.info(f"新增合规规则: {rule.rule_code} by user {current_user['id']}")
    await write_audit_log(
        user_id=current_user["id"], action="rule_create",
        resource_type="compliance_rule", resource_id=str(rule.id),
        after_value=rule.to_dict(),
    )
    return success(rule.to_dict())


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    request: dict,
    current_user: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """编辑合规规则"""
    rule = db.query(ComplianceRule).filter(ComplianceRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    # 按"编辑后的合并结果"整体校验：防止改类型/改 patterns 时留下非法规则
    _validate_rule_fields({**rule.to_dict(), **request}, partial=False)

    changed_fields = ["rule_name", "rule_type", "content", "severity", "action", "description", "enabled"]
    before_value = {f: getattr(rule, f) for f in changed_fields if f in request}
    for field in changed_fields:
        if field in request:
            setattr(rule, field, request[field])
    rule.version = (rule.version or 0) + 1

    db.commit()
    checker.reload()  # 让本 worker 立即生效（其他 worker 靠 TTL 自动重载）
    logger.info(f"更新合规规则: {rule.rule_code} v{rule.version}")
    await write_audit_log(
        user_id=current_user["id"], action="rule_update",
        resource_type="compliance_rule", resource_id=str(rule.id),
        before_value=before_value,
        after_value={f: getattr(rule, f) for f in before_value},
    )
    return success(rule.to_dict())


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_user: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """禁用合规规则（软删除，不物理删除）"""
    rule = db.query(ComplianceRule).filter(ComplianceRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.enabled = False
    db.commit()
    checker.reload()  # 让本 worker 立即生效（其他 worker 靠 TTL 自动重载）
    logger.info(f"禁用合规规则: {rule.rule_code}")
    await write_audit_log(
        user_id=current_user["id"], action="rule_disable",
        resource_type="compliance_rule", resource_id=str(rule.id),
        before_value={"enabled": True},
        after_value={"enabled": False},
    )
    return success(None, "规则已禁用")


# ==================== 规则热更新 & 测试 ====================

@router.post("/rules/reload")
async def reload_rules(current_user: dict = Depends(require_roles(*RULE_ADMIN_ROLES))):
    """热更新规则缓存（不重启服务）"""
    before = len(checker.rules)
    checker.reload()
    await write_audit_log(
        user_id=current_user["id"], action="rules_reload",
        resource_type="compliance_rule",
        before_value={"rules": before},
        after_value={"rules": len(checker.rules)},
    )
    return success({"reloaded_rules": len(checker.rules)})


@router.post("/rules/test")
async def test_rule(request: dict, current_user: dict = Depends(require_roles(*RULE_ADMIN_ROLES))):
    """测试规则：输入文本，查看命中哪些规则"""
    content = request.get("content", "")
    rule_code = request.get("rule_code")
    if not content:
        raise ParamError("content 不能为空")
    result = checker.test_rule(content, rule_code)
    return success(result)


# ==================== 拦截记录 ====================

@router.get("/blocks/stats")
async def blocks_stats(
    days: int = Query(7, ge=1, le=90, description="统计最近 N 天（仪表盘热力图）"),
    _admin: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """合规拦截聚合：区域 × 日期 热力图数据（驾驶舱"风险热力图"数据源）。

    区域维度：compliance_blocks.user_id join users.region 获得 ——
    shared.models.user.User 各服务共用，且 compliance-service 与 auth-service
    使用同一 shared/common/db_session.py（同一 DATABASE_URL，同库直连），
    直接可 join；若独立库部署导致 users 不可达（ProgrammingError 等），
    自动降级为 service_name 维度兜底（注意 M31：service_name 实为内容类型
    user_input/ai_output，兜底值仅供参考），dimension 字段告知前端实际维度。
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func as sqlfunc
    from shared.models.user import User

    since = datetime.utcnow() - timedelta(days=days)
    dimension = "region"
    try:
        rows = (
            db.query(
                sqlfunc.coalesce(User.region, "未分配").label("region"),
                sqlfunc.date(ComplianceBlock.blocked_at).label("date"),
                sqlfunc.count(ComplianceBlock.id),
            )
            .outerjoin(User, ComplianceBlock.user_id == User.id)
            .filter(ComplianceBlock.blocked_at >= since)
            .group_by(User.region, sqlfunc.date(ComplianceBlock.blocked_at))
            .all()
        )
        items = [{"region": r[0] or "未知", "date": str(r[1]), "count": r[2]} for r in rows]
    except Exception as exc:
        # 降级路径：users 表不可达（独立库部署）时按 service_name 维度聚合
        logger.warning("blocks/stats join users 失败，降级为 service 维度: %s", exc)
        dimension = "service"
        rows = (
            db.query(
                sqlfunc.coalesce(ComplianceBlock.service_name, "unknown").label("svc"),
                sqlfunc.date(ComplianceBlock.blocked_at).label("date"),
                sqlfunc.count(ComplianceBlock.id),
            )
            .filter(ComplianceBlock.blocked_at >= since)
            .group_by(ComplianceBlock.service_name, sqlfunc.date(ComplianceBlock.blocked_at))
            .all()
        )
        items = [{"region": r[0] or "未知", "date": str(r[1]), "count": r[2]} for r in rows]

    return success({"dimension": dimension, "days": days, "items": items})


@router.get("/blocks/{block_id}")
async def get_block_detail(
    block_id: int,
    _admin: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """拦截记录详情：完整内容 + 上下文（列表接口 content 截断到 200 字、不含 context）"""
    block = db.query(ComplianceBlock).filter(ComplianceBlock.id == block_id).first()
    if not block:
        raise ParamError("拦截记录不存在")
    return success({
        "id": block.id,
        "user_id": block.user_id,
        "service_name": block.service_name,
        "content": block.content or "",
        "rule_code": block.rule_code,
        "rule_name": block.rule_name,
        "severity": block.severity,
        "action": block.action,
        "context": block.context,
        "blocked_at": block.blocked_at.isoformat() if block.blocked_at else None,
    })


@router.get("/blocks")
async def list_blocks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    rule_code: Optional[str] = Query(None),
    _admin: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """拦截记录查询 —— 含他人 user_id 与内容片段，仅限规则管理员"""
    query = db.query(ComplianceBlock)
    if user_id:
        query = query.filter(ComplianceBlock.user_id == user_id)
    if rule_code:
        query = query.filter(ComplianceBlock.rule_code == rule_code)

    total = query.count()
    items = query.order_by(ComplianceBlock.blocked_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return success(paginate(
        [{
            "id": b.id,
            "user_id": b.user_id,
            "service_name": b.service_name,
            "content": b.content[:200] if b.content else "",  # 截断长文本
            "rule_code": b.rule_code,
            "rule_name": b.rule_name,
            "severity": b.severity,
            "action": b.action,
            "blocked_at": b.blocked_at.isoformat() if b.blocked_at else None,
        } for b in items],
        total=total, page=page, page_size=page_size
    ))


# ==================== 统计 ====================

@router.get("/stats")
async def compliance_stats(
    _admin: dict = Depends(require_roles(*RULE_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """合规统计数据"""
    from sqlalchemy import func as sqlfunc
    total_rules = db.query(sqlfunc.count(ComplianceRule.id)).scalar()
    enabled_rules = db.query(sqlfunc.count(ComplianceRule.id)).filter(
        ComplianceRule.enabled == True
    ).scalar()
    # 简化统计
    return success({
        "total_rules": total_rules,
        "enabled_rules": enabled_rules,
        "loaded_memory_rules": len(checker.rules),
    })
