"""MAH 合规全景视图（三期 K，需求 3.7(4)）：备案状态分布 / 培训完成率 / 合规通过率。

口径：合规通过率 = 1 − rep 的分身对话中被拦截占比（join users.role=='rep' 的
assistant 行，2026-09-07 A-4 从全库对话收敛——MAH 是代表管理视角，医生的
medical_qa 对话不属被管理对象）。无对话时 1.0。
备案状态按 representative_qualifications 派生：无记录/无备案号 → not_filed；
audit_status=pending → pending_review；rejected → rejected；approved 且 filing 有效 → valid / 过期 → expired。"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.db_session import get_db
from shared.common.response import success
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.models.conversation import Conversation

router = APIRouter(prefix="/api/v1/specialists", tags=["mah-overview"])


def _filing_bucket(rep_id: int, qual: Optional[RepresentativeQualification]) -> str:
    """判序：审核状态（pending/rejected）优先于备案号有无——待审/被驳的资质即使无备案号也归对应桶。"""
    if not qual:
        return "not_filed"
    if qual.audit_status == "pending":
        return "pending_review"
    if qual.audit_status == "rejected":
        return "rejected"
    if not (qual.filing_number or "").strip():
        return "not_filed"
    if qual.filing_expire_date and qual.filing_expire_date < date.today():
        return "expired"
    return "valid"


@router.get("/mah-overview")
async def mah_overview(
    _admin: dict = Depends(require_roles("admin", "manager", "compliance")),
    db: Session = Depends(get_db),
):
    reps = db.query(User).filter(User.role == "rep").all()
    quals = db.query(RepresentativeQualification).all()
    qual_map = {q.representative_id: q for q in quals}

    filing = {"not_filed": 0, "valid": 0, "expired": 0, "pending_review": 0, "rejected": 0}
    for rep in reps:
        filing[_filing_bucket(rep.id, qual_map.get(rep.id))] += 1

    approved_quals = [q for q in quals if q.audit_status == "approved"]
    total_reps = len(reps) or 1
    training_completed = sum(1 for q in approved_quals if q.compliance_training_completed)
    commitment_signed = sum(1 for q in approved_quals if q.commitment_signed)

    # 合规通过率口径（2026-09-07 A-4 收敛）：rep 的分身对话（join users.role=='rep'）的
    # assistant 行（一轮一行，compliance_result 落在 assistant 行——与 review-queue 同
    # 行级口径）。此前分母是全库全部消息行：①医生的 medical_qa 对话计入分母，但医生
    # 不是被 MAH 管理的代表，数字被无关行摊薄；②user 行无 compliance_result 也计入，
    # 行级口径下稀释了拦截占比。排除 visit_prep_ 机器会话（prep 指令被拦会虚增 blocked）。
    # 医生行整体排除后，medical 拦截不落库（medical.py 被拦只写审计）不再影响本指标。
    from shared.common.conventions import not_prep_session
    conv_rows = (
        db.query(Conversation.compliance_result)
        .join(User, User.id == Conversation.user_id)
        .filter(
            User.role == "rep",
            Conversation.role == "assistant",
            not_prep_session(Conversation.session_id),
        )
        .all()
    )
    total_conv = len(conv_rows)
    blocked = sum(1 for (cr,) in conv_rows if cr and cr.get("blocked"))
    compliance_pass_rate = round(1 - (blocked / total_conv), 4) if total_conv else 1.0

    return success({
        "total_reps": len(reps),
        "filing": filing,
        "training_completed_rate": round(training_completed / total_reps, 4),
        "commitment_signed_rate": round(commitment_signed / total_reps, 4),
        "compliance_pass_rate": compliance_pass_rate,
    })
