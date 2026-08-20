"""MAH 合规全景视图（三期 K，需求 3.7(4)）：备案状态分布 / 培训完成率 / 合规通过率。

口径：合规通过率 = 1 − conversations.compliance_result.blocked=true / 总对话数（同 review-queue）。
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

    conv_rows = db.query(Conversation.compliance_result).all()
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
