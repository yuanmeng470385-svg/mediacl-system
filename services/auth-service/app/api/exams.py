"""题库与考试（需求文档 3.4(2)(3)）：医学部/合规部人工审核题目；代表端在线考试"""
import logging
import random
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user, require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import BusinessError, ParamError, PermissionError, success
from shared.models.training_exam import ExamQuestion, ExamRecord

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/exams", tags=["exams"])

EXAM_ADMIN_ROLES = ("admin", "manager", "compliance", "medical")
VALID_TYPES = ("single", "multiple", "judge")
VALID_REVIEW = ("pending", "approved", "rejected")


def _validate_question(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    qtype = (payload.get("question_type") or "").strip()
    if qtype not in VALID_TYPES:
        raise ParamError("question_type 必须是 single/multiple/judge 之一")
    content = (payload.get("content") or "").strip()
    if not content:
        raise ParamError("题目内容不能为空")
    options = payload.get("options")
    if not isinstance(options, list) or len(options) < 2:
        raise ParamError("options 必须是至少 2 个选项的数组")
    if not all(isinstance(o, str) and o.strip() for o in options):
        raise ParamError("选项必须是非空字符串")
    answer = payload.get("answer")
    if not isinstance(answer, list) or not answer:
        raise ParamError("answer 必须是正确选项索引数组，如 [0] 或 [1,2]")
    if not all(isinstance(i, int) for i in answer):
        raise ParamError("answer 元素必须是整数索引")
    if any(i < 0 or i >= len(options) for i in answer):
        raise ParamError("answer 索引超出选项范围")
    if qtype in ("single", "judge") and len(answer) != 1:
        raise ParamError("single/judge 题目 answer 必须只有一个选项")
    return {
        "question_type": qtype,
        "content": content,
        "options": [str(o).strip() for o in options],
        "answer": sorted(set(answer)),
    }


# ---------------- 题库管理（管理端） ----------------

@router.post("/questions")
async def create_question(
    payload: dict,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    data = _validate_question(payload)
    q = ExamQuestion(
        material_id=payload.get("material_id"),
        question_type=data["question_type"],
        content=data["content"],
        options=data["options"],
        answer=data["answer"],
        review_status="pending",
        created_by=current_user["id"],
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    await write_audit_log(
        action="exam_question_create",
        user_id=current_user["id"],
        resource_type="exam_question",
        resource_id=str(q.id),
        request_id=get_request_id() or None,
    )
    return success(q.to_dict())


@router.get("/questions")
async def list_questions(
    page: int = 1,
    page_size: int = 20,
    review_status: Optional[str] = None,
    material_id: Optional[int] = None,
    keyword: Optional[str] = None,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    if review_status and review_status not in VALID_REVIEW:
        raise ParamError("review_status 不合法")
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(ExamQuestion)
    if review_status:
        query = query.filter(ExamQuestion.review_status == review_status)
    if material_id:
        query = query.filter(ExamQuestion.material_id == material_id)
    if keyword:
        query = query.filter(ExamQuestion.content.ilike(f"%{keyword}%"))
    total = query.count()
    rows = query.order_by(ExamQuestion.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([q.to_dict() for q in rows], total, p.page, p.page_size))


@router.put("/questions/{question_id}")
async def update_question(
    question_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    q = db.query(ExamQuestion).filter(ExamQuestion.id == question_id).first()
    if not q:
        raise BusinessError("题目不存在", code=4001)
    if q.review_status == "approved":
        raise BusinessError("已审核通过的题目不可修改，请先驳回或重建", code=4001)
    data = _validate_question(payload)
    q.question_type = data["question_type"]
    q.content = data["content"]
    q.options = data["options"]
    q.answer = data["answer"]
    if "material_id" in payload:
        q.material_id = payload.get("material_id")
    db.commit()
    db.refresh(q)
    await write_audit_log(
        action="exam_question_update",
        user_id=current_user["id"],
        resource_type="exam_question",
        resource_id=str(q.id),
        request_id=get_request_id() or None,
    )
    return success(q.to_dict())


@router.post("/questions/{question_id}/review")
async def review_question(
    question_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    q = db.query(ExamQuestion).filter(ExamQuestion.id == question_id).first()
    if not q:
        raise BusinessError("题目不存在", code=4001)
    if q.review_status != "pending":
        raise BusinessError("当前状态不可审核（仅待审核可审）", code=4001)
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    verdict = payload.get("verdict")
    if verdict not in ("approve", "reject"):
        raise ParamError("verdict 必须是 approve 或 reject")
    reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    if verdict == "reject" and not reason:
        raise ParamError("驳回必须填写原因")
    if len(reason) > 500:
        raise ParamError("原因长度不能超过 500 字符")
    q.review_status = "approved" if verdict == "approve" else "rejected"
    q.review_reason = reason if verdict == "reject" else None
    q.reviewed_by = current_user["id"]
    q.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(q)
    await write_audit_log(
        action="exam_question_review",
        user_id=current_user["id"],
        resource_type="exam_question",
        resource_id=str(q.id),
        after_value={"review_status": q.review_status, "review_reason": q.review_reason},
        request_id=get_request_id() or None,
    )
    return success(q.to_dict())
