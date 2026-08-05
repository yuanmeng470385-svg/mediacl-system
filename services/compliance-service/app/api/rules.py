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
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """规则列表（分页、筛选）"""
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
    rule = ComplianceRule(
        rule_code=rule_code,
        rule_name=rule_name,
        rule_type=request.get("rule_type") or "keyword",
        content=request.get("content", {}),
        severity=request.get("severity", "high"),
        action=request.get("action", "reject"),
        description=request.get("description", ""),
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

@router.get("/blocks")
async def list_blocks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    rule_code: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """拦截记录查询"""
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
    current_user: dict = Depends(get_current_user),
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
