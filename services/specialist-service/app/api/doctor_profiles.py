"""医生学术偏好引擎（需求 5.4）：自动学习 + 个性化学术简报 + 可关闭"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import ParamError, success
from shared.models.doctor_profile import DoctorProfile

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/doctor-profiles", tags=["doctor-profiles"])

VALID_DOC_TYPES = ("guideline", "rct", "real_world", "case_report")
VALID_STYLES = ("简洁", "标准", "详尽")

_AREA_KEYWORDS = {
    "心血管": ["高血压", "冠心病", "心衰", "心内科", "降压"],
    "肿瘤": ["肿瘤", "癌症", "癌", "化疗", "免疫治疗"],
    "内分泌": ["糖尿病", "甲状腺", "内分泌", "血糖"],
    "呼吸": ["哮喘", "慢阻肺", "呼吸", "肺"],
    "神经": ["脑卒中", "帕金森", "神经", "癫痫"],
}


def _infer_doc_type(history: list) -> Optional[str]:
    """从问题文本关键词推断文献类型偏好（citations 无 doc_type 字段，不可靠）"""
    counts = {}
    for row in history:
        text = (row.content or "")
        if any(k in text for k in ("指南", "共识", "指导原则")):
            counts["guideline"] = counts.get("guideline", 0) + 1
        if any(k in text for k in ("临床试验", "研究", "RCT", "随机")):
            counts["rct"] = counts.get("rct", 0) + 1
        if any(k in text for k in ("真实世界", "病例报告", "个案")):
            counts["real_world"] = counts.get("real_world", 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _infer_interest_areas(history: list) -> list:
    areas = []
    for row in history:
        text = (row.content or "").lower()
        for area, kws in _AREA_KEYWORDS.items():
            if any(kw.lower() in text for kw in kws) and area not in areas:
                areas.append(area)
    return areas[:5]


def _infer_style(history: list) -> str:
    # 简化：平均回答长度推断（问答历史里 assistant 行长→详尽）
    lengths = []
    for row in history:
        if row.role == "assistant" and row.content:
            lengths.append(len(row.content))
    if not lengths:
        return "标准"
    avg = sum(lengths) / len(lengths)
    if avg < 200:
        return "简洁"
    if avg < 600:
        return "标准"
    return "详尽"


@router.get("")
async def get_profile(
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    prof = db.query(DoctorProfile).filter(DoctorProfile.doctor_id == current_user["id"]).first()
    return success(prof.to_dict() if prof else None)


@router.put("")
async def update_profile(
    payload: dict,
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    prof = db.query(DoctorProfile).filter(DoctorProfile.doctor_id == current_user["id"]).first()
    if not prof:
        prof = DoctorProfile(doctor_id=current_user["id"])
        db.add(prof)
    if "interest_areas" in payload:
        areas = payload["interest_areas"]
        if not isinstance(areas, list) or not all(isinstance(a, str) for a in areas):
            raise ParamError("interest_areas 必须是字符串数组")
        prof.interest_areas = areas
    if "preferred_doc_type" in payload:
        t = payload["preferred_doc_type"]
        if t is not None and t not in VALID_DOC_TYPES:
            raise ParamError("preferred_doc_type 不合法")
        prof.preferred_doc_type = t
    if "preferred_style" in payload:
        s = payload["preferred_style"]
        if s is not None and s not in VALID_STYLES:
            raise ParamError("preferred_style 不合法")
        prof.preferred_style = s
    if "closed" in payload:
        if not isinstance(payload["closed"], bool):
            raise ParamError("closed 必须是布尔值")
        prof.closed = payload["closed"]
    db.commit()
    db.refresh(prof)
    await write_audit_log(
        action="doctor_profile_update",
        user_id=current_user["id"],
        resource_type="doctor_profile",
        resource_id=str(prof.id),
        after_value={"closed": prof.closed, "interest_areas": prof.interest_areas},
        request_id=get_request_id() or None,
    )
    return success(prof.to_dict())


@router.post("/learn")
async def learn_profile(
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """从本人 medical_qa 对话历史自动学习偏好（仅本人数据，患者数据零采集）"""
    from app.models.conversation import Conversation

    prof = db.query(DoctorProfile).filter(DoctorProfile.doctor_id == current_user["id"]).first()
    if prof and prof.closed:
        return success(prof.to_dict())  # 关闭个性化不学习

    history = db.query(Conversation).filter(
        Conversation.user_id == current_user["id"],
    ).order_by(Conversation.id.desc()).limit(50).all()

    doc_type = _infer_doc_type(history)
    areas = _infer_interest_areas(history)
    style = _infer_style(history)

    if not prof:
        prof = DoctorProfile(doctor_id=current_user["id"])
        db.add(prof)
    if doc_type:
        prof.preferred_doc_type = doc_type
    if areas:
        prof.interest_areas = list(dict.fromkeys((prof.interest_areas or []) + areas))[:5]
    prof.preferred_style = style
    db.commit()
    db.refresh(prof)
    return success(prof.to_dict())


@router.get("/briefing")
async def get_briefing(
    current_user: dict = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """个性化学术简报（需求 5.4(2)）：基于偏好返回内容（简化：返回兴趣领域相关关键词建议）"""
    prof = db.query(DoctorProfile).filter(DoctorProfile.doctor_id == current_user["id"]).first()
    if not prof or prof.closed or not prof.interest_areas:
        return success({"items": [], "personalized": False})
    items = [{
        "area": a,
        "suggestion": f"关注 {a} 领域最新指南与临床研究",
        "doc_type": prof.preferred_doc_type or "guideline",
    } for a in prof.interest_areas]
    return success({"items": items, "personalized": True})
