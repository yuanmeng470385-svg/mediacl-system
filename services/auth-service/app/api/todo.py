"""管理端待办中心（2026-09-15 C 批）：auth 侧四类待办计数。

与 specialist 侧 /api/v1/specialists/todo-summary 配对，web 待办中心并行拉取聚合，
侧边栏红色徽标 = 两端合计。计数只读不分页；标签/跳转路径在前端按角色解析
（后端不掺 UI 语义）。privacy 计 pending+processing（两者都未办结，30 日 SLA 口径）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.response import success
from shared.models.doctor import DoctorCertification
from shared.models.privacy import PrivacyRequest
from shared.models.qualification import RepresentativeQualification
from shared.models.training_exam import ExamQuestion

router = APIRouter(prefix="/api/v1/auth", tags=["auth-todo"])


@router.get("/todo-summary")
async def todo_summary(
    current_user: dict = Depends(require_roles("admin", "manager", "compliance", "medical")),
    db: Session = Depends(get_db),
):
    """管理端待办计数（auth 侧）：资质待审 / 医生认证待审 / 隐私请求未办结 / 考试题待审。"""
    items = [
        {
            "key": "qualification_pending",
            "count": db.query(RepresentativeQualification)
            .filter(RepresentativeQualification.audit_status == "pending").count(),
        },
        {
            "key": "doctor_cert_pending",
            "count": db.query(DoctorCertification)
            .filter(DoctorCertification.cert_status == "pending").count(),
        },
        {
            "key": "privacy_open",
            "count": db.query(PrivacyRequest)
            .filter(PrivacyRequest.status.in_(("pending", "processing"))).count(),
        },
        {
            "key": "exam_question_pending",
            "count": db.query(ExamQuestion)
            .filter(ExamQuestion.review_status == "pending").count(),
        },
    ]
    return success({"items": items})
