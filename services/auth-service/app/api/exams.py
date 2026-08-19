"""题库与考试（需求文档 3.4(2)(3)）：医学部/合规部人工审核题目；代表端在线考试"""
import asyncio
import logging
import os
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
from shared.models.training_exam import ExamQuestion, ExamRecord, TrainingMaterial
from shared.models.qualification import RepresentativeQualification

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/exams", tags=["exams"])

EXAM_ADMIN_ROLES = ("admin", "manager", "compliance", "medical")
VALID_TYPES = ("single", "multiple", "judge")
VALID_REVIEW = ("pending", "approved", "rejected")

_PASS_SCORE = int(os.getenv("EXAM_PASS_SCORE", "80"))


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
    # 重新送审语义：pending/rejected 题目被编辑后重置为待审核，清空上一轮审核信息
    # （否则被驳回的题修正后仍是 rejected，而 review 仅 pending 可审 → 永久无法重新送审）
    q.review_status = "pending"
    q.review_reason = None
    q.reviewed_by = None
    q.reviewed_at = None
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


from app.services.qwen_client import QwenExamClient


@router.post("/questions/ai-generate")
async def ai_generate_questions(
    payload: dict,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """AI 出题草稿（不落库）。管理端预览确认后走正常入库 + 人工审核。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    material_id = payload.get("material_id")
    mat = db.query(TrainingMaterial).filter(TrainingMaterial.id == material_id).first() if material_id else None
    if not mat or mat.status != "active":
        raise BusinessError("培训材料不存在", code=4001)
    count = payload.get("count") or 5
    if not isinstance(count, int) or not (1 <= count <= 20):
        raise ParamError("count 必须是 1-20 的整数")
    qtype = payload.get("question_type") or "single"
    if qtype not in VALID_TYPES:
        raise ParamError("question_type 不合法")
    try:
        result = await asyncio.to_thread(
            QwenExamClient().generate_questions, mat.content, count, qtype
        )
    except Exception as exc:  # 出题失败不阻塞人工录入
        logger.warning(f"AI 出题失败: {exc}")
        raise BusinessError(f"AI 出题失败：{exc}", code=6001)
    questions = result.get("questions", []) if isinstance(result, dict) else []
    drafts = []
    for raw in questions:
        if not isinstance(raw, dict):
            continue
        try:
            drafts.append(_validate_question(raw))
        except ParamError:
            continue  # 单条草稿不合规跳过，不整体失败
    return success(drafts)


# ---------------- 考试（代表端） ----------------

def _score_match(selected: list, answer: list) -> bool:
    """判分：按集合相等（排序后比较），多选必须全对。"""
    if not isinstance(selected, list):
        return False
    try:
        return sorted(int(i) for i in selected) == sorted(int(a) for a in answer)
    except (TypeError, ValueError):
        return False


@router.post("/start")
async def start_exam(
    payload: dict,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """开始考试：从 approved 题目随机抽题（默认 10 道，最多 30），不含答案。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    question_count = payload.get("question_count") or 10
    if not isinstance(question_count, int) or not (1 <= question_count <= 30):
        raise ParamError("question_count 必须是 1-30 的整数")
    pool = db.query(ExamQuestion).filter(ExamQuestion.review_status == "approved").all()
    if not pool:
        raise BusinessError("暂无可考试的题目，请联系医学部/合规部上架题目", code=4001)
    questions = random.sample(pool, min(question_count, len(pool)))
    return success({"questions": [q.to_dict() for q in questions]})


@router.post("/submit")
async def submit_exam(
    payload: dict,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """提交考试：判分 + 写 exam_records + 回写 representative_qualifications 三字段。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    answers = payload.get("answers")
    if not isinstance(answers, list) or not answers:
        raise ParamError("answers 必须是题目作答数组")
    q_ids = [a.get("question_id") for a in answers if isinstance(a, dict)]
    if not q_ids:
        raise ParamError("answers 缺少 question_id")
    rows = db.query(ExamQuestion).filter(ExamQuestion.id.in_(q_ids)).all()
    by_id = {q.id: q for q in rows}
    if len(rows) != len(set(q_ids)):
        raise BusinessError("存在不存在的题目", code=4001)
    if any(q.review_status != "approved" for q in rows):
        raise BusinessError("存在未上架的题目，请重新开始考试", code=4001)

    correct = 0
    for a in answers:
        q = by_id.get(a.get("question_id"))
        if q is None:
            raise BusinessError("存在不存在的题目", code=4001)
        if _score_match(a.get("selected"), q.answer):
            correct += 1
    total = len(answers)
    score = round(correct * 100 / total)
    passed = score >= _PASS_SCORE

    record = ExamRecord(
        representative_id=current_user["id"],
        question_count=total,
        correct_count=correct,
        score=score,
        passed=passed,
    )
    db.add(record)
    # 回写代表资质表
    qual = db.query(RepresentativeQualification).filter(
        RepresentativeQualification.representative_id == current_user["id"]
    ).first()
    if qual:
        if qual.compliance_exam_score is None or score > qual.compliance_exam_score:
            qual.compliance_exam_score = score
        if passed:
            qual.compliance_training_completed = True
    db.commit()
    db.refresh(record)
    await write_audit_log(
        action="exam_submit",
        user_id=current_user["id"],
        resource_type="exam_record",
        resource_id=str(record.id),
        after_value={"score": score, "passed": passed, "question_count": total},
        request_id=get_request_id() or None,
    )
    return success(record.to_dict())


@router.get("/records/me")
async def my_exam_records(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(ExamRecord).filter(ExamRecord.representative_id == current_user["id"])
    total = query.count()
    rows = query.order_by(ExamRecord.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([r.to_dict() for r in rows], total, p.page, p.page_size))


@router.get("/records")
async def list_exam_records(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles(*EXAM_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    p = PaginationParams(page=page, page_size=page_size)
    query = db.query(ExamRecord)
    total = query.count()
    rows = query.order_by(ExamRecord.id.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate([r.to_dict() for r in rows], total, p.page, p.page_size))
