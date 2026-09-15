"""管理端待办中心（2026-09-15 C 批）：specialist 侧四类待办计数。

与 auth 侧 /api/v1/auth/todo-summary 配对，web 待办中心并行拉取聚合。
计数口径与各审核队列列表端点一致（同一个状态过滤条件）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.response import success
from shared.models.patient_edu import EduContentRecord
from shared.models.practice import ObjectionScript
from shared.models.skill import SkillPackage

from app.models.export_request import ExportRequest

router = APIRouter(prefix="/api/v1/specialists", tags=["specialist-todo"])


@router.get("/todo-summary")
async def todo_summary(
    current_user: dict = Depends(require_roles("admin", "manager", "compliance", "medical")),
    db: Session = Depends(get_db),
):
    """管理端待办计数（specialist 侧）：Skill 待审 / 患教待审 / 异议话术待审 / 数据导出待批。

    ⚠ 必须注册在 GET /{specialist_id} 之前（同 style-sources/monitor）——
    一段式静态路径，否则被动态段吞掉，int 转换失败 422 渲染成 code 1000。"""
    items = [
        {
            "key": "skill_package_pending",
            "count": db.query(SkillPackage)
            .filter(SkillPackage.audit_status == "pending").count(),
        },
        {
            "key": "patient_edu_pending",
            "count": db.query(EduContentRecord)
            .filter(EduContentRecord.audit_status == "pending").count(),
        },
        {
            "key": "objection_script_pending",
            "count": db.query(ObjectionScript)
            .filter(ObjectionScript.review_status == "pending").count(),
        },
        {
            "key": "data_export_pending",
            "count": db.query(ExportRequest)
            .filter(ExportRequest.status == "pending").count(),
        },
    ]
    return success({"items": items})
