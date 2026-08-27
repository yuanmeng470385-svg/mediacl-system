"""医生学术偏好 → 个性化排序/提示的共享工具（spec 2026-08-27）。

红线：医学事实零扰动。reorder_results 只改顺序不改集合；
preference_context 必带「不得改变医学事实」硬约束。
closed=true / 偏好为空 / 读取异常 → 一律回退基线。
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from shared.models.doctor_profile import DoctorProfile


def get_profile(db: Session, doctor_id: int) -> Optional[DoctorProfile]:
    """读医生偏好画像；closed 或空兴趣 → None（调用方回退基线）。"""
    p = db.query(DoctorProfile).filter(DoctorProfile.doctor_id == doctor_id).first()
    return p if (p and not p.closed and p.interest_areas) else None


def get_profiles_batch(db: Session, doctor_ids: List[int]) -> Dict[int, Optional[DoctorProfile]]:
    """批量读（IN 一次查询），未查到的医生不在 dict（调用方按无偏好处理）。"""
    if not doctor_ids:
        return {}
    rows = db.query(DoctorProfile).filter(DoctorProfile.doctor_id.in_(doctor_ids)).all()
    return {r.doctor_id: r for r in rows if r and not r.closed and r.interest_areas}


def _areas(profile) -> List[str]:
    return [str(a).lower() for a in (profile.interest_areas or []) if a]


def reorder_results(results: List[Dict], profile: Optional[DoctorProfile]) -> List[Dict]:
    """按偏好稳定重排（集合不变只变顺序）；closed/空/无 profile 原序返回。"""
    if not profile or profile.closed or not results:
        return results
    areas = _areas(profile)

    def score(r: Dict) -> int:
        text = f"{r.get('title', '')} {r.get('content', '')}".lower()
        s = sum(1 for a in areas if a and a in text)
        dt = str(r.get("doc_type") or "")
        if profile.preferred_doc_type and dt and dt == profile.preferred_doc_type:
            s += 1
        return s

    return sorted(results, key=lambda r: -score(r))  # sorted 稳定：同权重保持原序


def matched_interest(card_title: str, profile: Optional[DoctorProfile]) -> bool:
    """卡片标题是否命中医生兴趣领域；closed/无 profile → False。"""
    if not profile or profile.closed or not card_title:
        return False
    areas = _areas(profile)
    t = str(card_title).lower()
    return any(a and a in t for a in areas)


def preference_context(profile: Optional[DoctorProfile]) -> str:
    """偏好 → prompt 注入片段（含事实约束）；closed/空 → 空串。"""
    if not profile or profile.closed:
        return ""
    parts = []
    areas = [str(a) for a in (profile.interest_areas or []) if a]
    if areas:
        parts.append(f"该医生主要关注领域：{'、'.join(areas)}")
    if profile.preferred_style:
        parts.append(f"回答风格偏好：{profile.preferred_style}")
    if not parts:
        return ""
    return (
        "（医生学术偏好上下文——仅供组织回答侧重，"
        "不得改变医学事实、不得省略关键信息：" + "；".join(parts) + "）"
    )
