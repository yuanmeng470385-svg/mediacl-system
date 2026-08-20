"""数据分类分级清单（三期 K，需求 3.8(1)）：只读配置，三类数据资产映射实际表。
敏感类别（个人信息/对话明细）导出必走数据导出审批流（/data-exports）。"""
from fastapi import APIRouter, Depends

from shared.common.auth import require_roles
from shared.common.response import success

router = APIRouter(prefix="/api/v1/compliance", tags=["data-assets"])

ASSETS = [
    {"category": "个人信息", "level": "敏感", "tables": ["users", "doctor_profiles", "doctor_twin_subscriptions", "doctor_consents"]},
    {"category": "业务数据", "level": "内部", "tables": ["conversations", "academic_cards", "card_push_records", "edu_content_records", "visit_records"]},
    {"category": "合规留存数据", "level": "审计留存", "tables": ["audit_logs", "compliance_blocks", "compliance_rules", "skill_audits"]},
]


@router.get("/data-assets")
async def data_assets(
    _admin: dict = Depends(require_roles("admin", "manager", "compliance")),
):
    return success(ASSETS)
