"""数字专员服务 API 路由"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from shared.common.response import success, ParamError
from shared.common.auth import get_current_user, require_roles
from shared.common.pagination import PaginationParams, paginate
from app.services.audit_client import write_audit_log
from shared.common.db_session import get_db
from app.models.specialist import Specialist
from app.core.answer_generator import AnswerGenerator

router = APIRouter(prefix="/api/v1/specialists", tags=["specialists"])
logger = logging.getLogger(__name__)


# ==================== 专员列表 & 详情 ====================

@router.get("")
async def list_specialists(
    page: int = 1,
    page_size: int = 20,
    status: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """专员列表（分页；status 可选过滤，缺省返回全部状态 —— web 需看 draft/disabled，mobile 展示时自行过滤）"""
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(Specialist)
    if status:
        q = q.filter(Specialist.status == status)
    total = q.count()
    items = q.order_by(Specialist.created_at.desc()).offset(p.offset).limit(p.limit).all()
    return success(paginate(
        [s.to_dict() for s in items], total=total, page=p.page, page_size=p.page_size
    ))


@router.get("/live-status")
async def get_live_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """数字员工办公室实时状态（web 后台 3s/5s 轮询）。

    状态推导：draft/disabled → offline；注册表有记录 → working（带阶段）；
    注册表空但进程刚启动（重启降级窗口）且 5 分钟内有过对话 → working（粗粒度 generating）；
    否则 idle（平时注册表空 = 立即空闲）。
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    from app.models.conversation import Conversation
    from app.core.activity_registry import (
        registry, PHASE_TEXT, PHASE_GENERATING, is_recently_started,
    )

    # 固定按 id 排序：3s/5s 轮询下卡片网格与前 8 工位条不得在两次轮询间换位
    specialists = db.query(Specialist).order_by(Specialist.id).all()
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    recent_cutoff = now - timedelta(minutes=5)

    # 今日对话数（role='user' 口径与 stats 一致）
    today_rows = db.query(
        Conversation.specialist_id, func.count(Conversation.id),
    ).filter(
        Conversation.role == "user",
        Conversation.created_at >= today_start,
    ).group_by(Conversation.specialist_id).all()
    today_count = {sid: cnt for sid, cnt in today_rows}

    # 最近活跃时间（任意 role 最后一条）
    active_rows = db.query(
        Conversation.specialist_id, func.max(Conversation.created_at),
    ).group_by(Conversation.specialist_id).all()
    last_active = {sid: ts for sid, ts in active_rows}

    # B5 修复（2026-08-12）：question_snippet 是别的用户正在问的问题内容 ——
    # 仅 admin/manager 可见（数据看板视角），普通角色（rep 等）剥离，防跨用户泄露
    can_see_snippet = current_user.get("role") in ("admin", "manager")

    items = []
    summary = {"working": 0, "idle": 0, "offline": 0}
    for s in specialists:
        snap = registry.get(s.id)
        if s.status in ("draft", "disabled"):
            state, phase = "offline", None
        elif snap is not None:
            state, phase = "working", snap.phase
        elif (is_recently_started()
              and last_active.get(s.id) is not None
              and last_active[s.id] >= recent_cutoff):
            state, phase = "working", PHASE_GENERATING
        else:
            state, phase = "idle", None
        summary[state] += 1
        items.append({
            "id": s.id,
            "name": s.name,
            "lifecycle": s.status,
            "state": state,
            "phase": phase,
            "phase_text": PHASE_TEXT.get(phase) if phase else None,
            "phase_since": snap.phase_since.isoformat() if snap else None,
            "question_snippet": snap.question_snippet if (snap and can_see_snippet) else None,
            "today_conversations": today_count.get(s.id, 0),
            # 规格：注册表 phase_since 或最近对话时间 —— 首次对话中（对话行未落库）注册表存在时展示阶段开始时刻
            "last_active_at": (
                snap.phase_since.isoformat()
                if snap is not None
                else last_active.get(s.id).isoformat() if last_active.get(s.id) else None
            ),
        })
    return success({"items": items, "summary": summary})


@router.get("/{specialist_id}")
async def get_specialist(
    specialist_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """专员详情"""
    specialist = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    return success(specialist.to_dict())


# ==================== 核心接口：与专员对话 ====================

def _persist_conversation(db, user_id: int, specialist_id: int,
                          question: str, result: dict):
    """落库问答两行，返回 assistant 行 id（反馈/收藏的主键）。

    入库失败不影响 chat 主流程 —— 返回 None，前端据此禁用反馈/收藏。
    """
    from app.models.conversation import Conversation
    try:
        conv = Conversation(
            user_id=user_id,
            specialist_id=specialist_id,
            session_id=result.get("session_id"),
            role="user",
            content=question,
        )
        db.add(conv)
        conv_ai = Conversation(
            user_id=user_id,
            specialist_id=specialist_id,
            session_id=result.get("session_id"),
            role="assistant",
            content=result.get("answer", ""),
            citations=result.get("citations"),
            compliance_result={"blocked": result.get("blocked")},
            latency_ms=result.get("latency_ms"),
        )
        db.add(conv_ai)
        db.commit()
        return conv_ai.id
    except Exception as e:
        logger.error(f"对话记录入库失败: {e}")
        db.rollback()
        return None


@router.post("/{specialist_id}/chat")
async def chat_with_specialist(
    specialist_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    与数字专员对话（核心接口）

    Request:
        {"question": "肺癌用药注意事项", "session_id": "上次对话ID（可选）"}

    Response:
        {"code":0, "data":{
            "answer": "...",
            "citations": [],
            "evidence_level": "B",
            "session_id": "...",
            "request_id": "...",
            "latency_ms": 1234,
            "blocked": false,
            "conversation_id": 42,
            "violations": []
        }}
    """
    # 验证专员存在
    specialist = db.query(Specialist).filter(
        Specialist.id == specialist_id,
        Specialist.status == "active"
    ).first()
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在或已停用")

    if not specialist.bailian_app_id:
        raise HTTPException(status_code=500, detail="专员尚未配置百炼 App ID")

    # 验证问题
    question = request.get("question", "").strip()
    if not question:
        raise ParamError("question 不能为空")

    session_id = request.get("session_id")

    # IDOR 防护：续传他人会话（session_id）统一 404，不泄露 session 是否存在
    if session_id:
        from app.api.conversations import assert_session_owner
        assert_session_owner(db, session_id, current_user["id"])

    # 调用答案生成器
    generator = AnswerGenerator()
    result = await generator.generate(
        question=question,
        specialist=specialist,
        user_id=current_user["id"],
        session_id=session_id,
    )

    # 对话记录入库 —— conversation_id 是前端反馈/收藏的主键
    result["conversation_id"] = _persist_conversation(
        db, current_user["id"], specialist_id, question, result
    )

    return success(result)


# ==================== 会话历史 ====================

@router.get("/conversations/{session_id}")
async def get_conversation_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取会话历史"""
    from app.models.conversation import Conversation
    from app.api.conversations import assert_session_owner
    # IDOR 防护：他人 session 统一 404，不泄露 session 是否存在
    assert_session_owner(db, session_id, current_user["id"])
    messages = db.query(Conversation).filter(
        Conversation.session_id == session_id
    ).order_by(Conversation.created_at).all()
    return success([m.to_dict() for m in messages])


# ==================== 使用统计 ====================

@router.get("/{specialist_id}/stats")
async def get_specialist_stats(
    specialist_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """专员使用统计（对话数 + 满意度）"""
    from app.models.conversation import Conversation
    from app.models.feedback import ConversationFeedback
    from sqlalchemy import func
    from app.api.conversations import compute_satisfaction

    specialist = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    # 每轮对话落库 user+assistant 两行 —— 只按 role='user' 计数避免双倍
    total = db.query(func.count(Conversation.id)).filter(
        Conversation.specialist_id == specialist_id,
        Conversation.role == "user",
    ).scalar()
    positive = db.query(func.count(ConversationFeedback.id)).filter(
        ConversationFeedback.specialist_id == specialist_id,
        ConversationFeedback.rating == 1,
    ).scalar()
    negative = db.query(func.count(ConversationFeedback.id)).filter(
        ConversationFeedback.specialist_id == specialist_id,
        ConversationFeedback.rating == -1,
    ).scalar()
    return success({"total_conversations": total or 0, **compute_satisfaction(positive or 0, negative or 0)})


@router.get("/{specialist_id}/feedback")
async def get_specialist_feedback(
    specialist_id: int,
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db),
):
    """专员反馈明细（B4 修复 2026-08-12：web 数据抽屉此前只有聚合统计，无明细接口）。

    G4（2026-08-13）：web 后台专用 —— 问答快照含全部用户的 question/answer，
    任意登录用户可读属越权（与 stats 等管理端点同口径），仅 admin/manager。

    返回该专员每条反馈（点赞/点踩）对应的问答快照：
      {id, conversation_id, rating(1/-1), comment, question, answer, citations, created_at}
    question = 同一会话（session_id）中排在锚点（反馈对应的 assistant 行）之前的最后一条 user 消息，
    与 toggle_favorite 的收藏快照取同轮逻辑一致。
    """
    from app.models.feedback import ConversationFeedback
    from app.models.conversation import Conversation

    specialist = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(ConversationFeedback).filter(ConversationFeedback.specialist_id == specialist_id)
    total = q.count()
    items = q.order_by(ConversationFeedback.id.desc()).offset(p.offset).limit(p.limit).all()

    rows = []
    for fb in items:
        conv = db.query(Conversation).filter(Conversation.id == fb.conversation_id).first()
        question = None
        if conv:
            prev_user = db.query(Conversation).filter(
                Conversation.session_id == conv.session_id,
                Conversation.role == "user",
                Conversation.id <= fb.conversation_id,
            ).order_by(Conversation.id.desc()).first()
            question = prev_user.content if prev_user else None
        rows.append({
            "id": fb.id,
            "conversation_id": fb.conversation_id,
            "rating": fb.rating,
            "comment": fb.comment,
            "question": question,
            "answer": conv.content if conv else None,
            "citations": conv.citations if conv else [],
            "created_at": fb.created_at.isoformat() if fb.created_at else None,
        })
    return success(paginate(rows, total=total, page=p.page, page_size=p.page_size))


SPECIALIST_UPDATE_FIELDS = {
    "name", "product_id", "persona", "knowledge_scope",
    "compliance_level", "bailian_app_id", "status",
}
VALID_STATUSES = {"draft", "active", "disabled"}


def _normalize_status(status: str) -> str:
    s = (status or "").strip().lower()
    if s not in VALID_STATUSES:
        raise ParamError(f"status 必须是 {'/'.join(sorted(VALID_STATUSES))}")
    return s


def _validate_specialist_fields(request: dict, creating: bool) -> dict:
    """白名单 + 必填校验（纯函数，便于单测）。

    creating 与 updating 都接受 SPECIALIST_UPDATE_FIELDS 白名单字段，
    白名单之外的字段一律 ParamError；creating 额外要求 name 与 product_id 非空。
    """
    allowed = set(request.keys()) - SPECIALIST_UPDATE_FIELDS
    if allowed:
        raise ParamError(f"不允许的字段: {sorted(allowed)}")
    if creating:
        name = (request.get("name") or "").strip()
        if not name:
            raise ParamError("name 不能为空")
        if not request.get("product_id"):
            raise ParamError("product_id 不能为空")
    return request


# ==================== 专员 CRUD（S6：仅 admin） ====================

@router.post("")
async def create_specialist(
    request: dict,
    current_user: dict = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """创建专员"""
    data = _validate_specialist_fields(request, creating=True)
    specialist = Specialist(
        name=data["name"].strip(),
        product_id=int(data["product_id"]),
        persona=data.get("persona"),
        knowledge_scope=data.get("knowledge_scope"),
        compliance_level=data.get("compliance_level", "internal"),
        bailian_app_id=data.get("bailian_app_id"),
        status=_normalize_status(data.get("status", "draft")),
    )
    db.add(specialist)
    db.commit()
    db.refresh(specialist)
    await write_audit_log(
        user_id=current_user["id"], action="specialist_create",
        resource_type="digital_specialist", resource_id=str(specialist.id),
        after_value=specialist.to_dict(),
    )
    return success(specialist.to_dict(), "专员已创建")


@router.put("/{specialist_id}")
async def update_specialist(
    specialist_id: int,
    request: dict,
    current_user: dict = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """编辑专员（仅白名单字段）"""
    specialist = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    data = _validate_specialist_fields(request, creating=False)
    for field in SPECIALIST_UPDATE_FIELDS:
        if field in data and data[field] is not None:
            value = _normalize_status(data[field]) if field == "status" else data[field]
            setattr(specialist, field, value)
    db.commit()
    db.refresh(specialist)
    await write_audit_log(
        user_id=current_user["id"], action="specialist_update",
        resource_type="digital_specialist", resource_id=str(specialist_id),
        after_value=specialist.to_dict(),
    )
    return success(specialist.to_dict())


@router.delete("/{specialist_id}")
async def disable_specialist(
    specialist_id: int,
    current_user: dict = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """停用专员（软删，status=disabled）"""
    specialist = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not specialist:
        raise HTTPException(status_code=404, detail="专员不存在")
    if specialist.status != "disabled":
        specialist.status = "disabled"
        db.commit()
    await write_audit_log(
        user_id=current_user["id"], action="specialist_disable",
        resource_type="digital_specialist", resource_id=str(specialist_id),
    )
    return success(None, "专员已停用")
