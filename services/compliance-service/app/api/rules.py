"""合规审核服务 API 路由"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from shared.common.response import success, error, ParamError
from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.pagination import paginate, PaginationParams
from sqlalchemy.orm import Session

from app.core.checker import get_checker
from shared.models.compliance import ComplianceRule, ComplianceBlock

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])
logger = logging.getLogger(__name__)

checker = get_checker()


# ==================== 合规检查（核心接口） ====================

@router.post("/check")
async def check_content(request: dict):
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
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新增合规规则"""
    rule = ComplianceRule(
        rule_code=request["rule_code"],
        rule_name=request["rule_name"],
        rule_type=request["rule_type"],
        content=request.get("content", {}),
        severity=request.get("severity", "high"),
        action=request.get("action", "reject"),
        description=request.get("description", ""),
        created_by=current_user["id"],
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    logger.info(f"新增合规规则: {rule.rule_code} by user {current_user['id']}")
    return success(rule.to_dict())


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑合规规则"""
    rule = db.query(ComplianceRule).filter(ComplianceRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    for field in ["rule_name", "rule_type", "content", "severity", "action", "description", "enabled"]:
        if field in request:
            setattr(rule, field, request[field])
    rule.version = (rule.version or 0) + 1

    db.commit()
    logger.info(f"更新合规规则: {rule.rule_code} v{rule.version}")
    return success(rule.to_dict())


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """禁用合规规则（软删除，不物理删除）"""
    rule = db.query(ComplianceRule).filter(ComplianceRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.enabled = False
    db.commit()
    logger.info(f"禁用合规规则: {rule.rule_code}")
    return success(None, "规则已禁用")


# ==================== 规则热更新 & 测试 ====================

@router.post("/rules/reload")
async def reload_rules(current_user: dict = Depends(get_current_user)):
    """热更新规则缓存（不重启服务）"""
    checker.reload()
    return success({"reloaded_rules": len(checker.rules)})


@router.post("/rules/test")
async def test_rule(request: dict, current_user: dict = Depends(get_current_user)):
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
