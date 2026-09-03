"""数字专员服务 API 路由"""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from shared.common.response import success, ParamError, BusinessError, PermissionError
from shared.common.auth import get_current_user, require_roles
from shared.common.pagination import PaginationParams, paginate
from app.services.audit_client import write_audit_log
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.conventions import VISIT_PREP_SESSION_PREFIX, not_prep_session
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


# ==================== 分身监控统计（web 分身监控页） ====================

@router.get("/monitor")
async def monitor_specialists(
    page: int = 1,
    page_size: int = 20,
    status: str = None,
    official: bool = None,
    current_user: dict = Depends(require_roles("admin", "manager", "compliance", "medical")),
    db: Session = Depends(get_db),
):
    """分身监控列表（分页，含统计字段）。

    在 Specialist.to_dict() 基础上附加（分批聚合，避免 N+1）：
    - today_services: 今日对话数（role='user'，created_at >= 今日 0 点）
    - avg_latency_ms: assistant 行 latency_ms 非空的平均值（无则 None）
    - service_doctors: doctor_twin_subscriptions 中 status='subscribed' 的 distinct doctor_id 数
    - added_count: doctor_twin_subscriptions 中该分身的行数
    - compliance_health: 近 30 天 assistant 对话中 compliance_result.blocked=true 占比
      （<5% → green，5-15% → yellow，>15% → red；无对话按 green）
    - approval_rate: conversation_feedback 中 rating=1 占比（0-1 float，无反馈 None）
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func, case
    from app.models.conversation import Conversation
    from app.models.feedback import ConversationFeedback
    from shared.models.doctor import DoctorTwinSubscription

    p = PaginationParams(page=page, page_size=page_size)
    q = db.query(Specialist)
    if status:
        q = q.filter(Specialist.status == status)
    if official is not None:
        q = q.filter(Specialist.is_official == official)
    total = q.count()
    specialists = q.order_by(Specialist.id.asc()).offset(p.offset).limit(p.limit).all()
    ids = [s.id for s in specialists]

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    stats = {sid: {} for sid in ids}

    if ids:
        # today_services（排除 visit_prep_ 机器会话，口径=真人服务数）
        rows = db.query(
            Conversation.specialist_id, func.count(Conversation.id),
        ).filter(
            Conversation.specialist_id.in_(ids),
            Conversation.role == "user",
            Conversation.created_at >= today_start,
            not_prep_session(Conversation.session_id),
        ).group_by(Conversation.specialist_id).all()
        for sid, cnt in rows:
            stats[sid]["today_services"] = cnt or 0

        # avg_latency_ms
        rows = db.query(
            Conversation.specialist_id, func.avg(Conversation.latency_ms),
        ).filter(
            Conversation.specialist_id.in_(ids),
            Conversation.role == "assistant",
            Conversation.latency_ms.isnot(None),
        ).group_by(Conversation.specialist_id).all()
        for sid, avg in rows:
            stats[sid]["avg_latency_ms"] = int(round(avg)) if avg is not None else None

        # service_doctors
        rows = db.query(
            DoctorTwinSubscription.twin_id,
            func.count(func.distinct(DoctorTwinSubscription.doctor_id)),
        ).filter(
            DoctorTwinSubscription.twin_id.in_(ids),
            DoctorTwinSubscription.status == "subscribed",
        ).group_by(DoctorTwinSubscription.twin_id).all()
        for sid, cnt in rows:
            stats[sid]["service_doctors"] = cnt or 0

        # added_count
        rows = db.query(
            DoctorTwinSubscription.twin_id, func.count(DoctorTwinSubscription.id),
        ).filter(
            DoctorTwinSubscription.twin_id.in_(ids),
        ).group_by(DoctorTwinSubscription.twin_id).all()
        for sid, cnt in rows:
            stats[sid]["added_count"] = cnt or 0

        # compliance_health（compliance_result 是 JSONB，跨方言用 Python 端解析；排除 prep 机器会话）
        rows = db.query(
            Conversation.specialist_id, Conversation.compliance_result,
        ).filter(
            Conversation.specialist_id.in_(ids),
            Conversation.role == "assistant",
            Conversation.created_at >= thirty_days_ago,
            not_prep_session(Conversation.session_id),
        ).all()
        health_agg = {sid: {"blocked": 0, "total": 0} for sid in ids}
        for sid, cr in rows:
            health_agg[sid]["total"] += 1
            if isinstance(cr, dict) and cr.get("blocked"):
                health_agg[sid]["blocked"] += 1
        for sid, agg in health_agg.items():
            if agg["total"] == 0:
                stats[sid]["compliance_health"] = "green"
            else:
                ratio = agg["blocked"] / agg["total"]
                stats[sid]["compliance_health"] = (
                    "red" if ratio > 0.15 else ("yellow" if ratio >= 0.05 else "green")
                )

        # approval_rate
        positive_expr = func.sum(case((ConversationFeedback.rating == 1, 1), else_=0))
        rows = db.query(
            ConversationFeedback.specialist_id,
            func.count(ConversationFeedback.id),
            positive_expr,
        ).filter(
            ConversationFeedback.specialist_id.in_(ids),
        ).group_by(ConversationFeedback.specialist_id).all()
        for sid, cnt, positive in rows:
            stats[sid]["approval_rate"] = round((positive or 0) / cnt, 4) if cnt else None

    items = []
    for s in specialists:
        d = s.to_dict()
        st = stats.get(s.id, {})
        d["today_services"] = st.get("today_services", 0)
        d["avg_latency_ms"] = st.get("avg_latency_ms")
        d["service_doctors"] = st.get("service_doctors", 0)
        d["added_count"] = st.get("added_count", 0)
        d["compliance_health"] = st.get("compliance_health", "green")
        d["approval_rate"] = st.get("approval_rate")
        items.append(d)

    return success(paginate(items, total=total, page=p.page, page_size=p.page_size))


# 待复核阈值（需求 3.2(3)：24 小时内拦截 ≥5 次标记待复核，可配置；与 compliance 同口径）
REVIEW_BLOCK_THRESHOLD = int(os.getenv("REVIEW_BLOCK_THRESHOLD", "5"))
REVIEW_WINDOW_HOURS = int(os.getenv("REVIEW_WINDOW_HOURS", "24"))


@router.get("/review-queue")
async def review_queue(
    current_user: dict = Depends(require_roles("admin", "manager", "compliance")),
    db: Session = Depends(get_db),
):
    """待复核名单（分身维度，人工裁决不做自动冻结）。

    按 conversations.compliance_result 中 blocked=true 且 created_at 在窗口内，
    以 specialist_id 聚合计数，count >= REVIEW_BLOCK_THRESHOLD 进入待复核——
    与 freeze/unfreeze 同为分身维度，待复核 → 冻结在同一页闭环。
    代表归属用 digital_specialists.representative_id join users；官方分身（无归属）rep_name 为 null。
    """
    from datetime import datetime, timedelta
    from app.models.conversation import Conversation
    from shared.models.user import User

    since = datetime.utcnow() - timedelta(hours=REVIEW_WINDOW_HOURS)
    rows = db.query(
        Conversation.specialist_id, Conversation.compliance_result,
    ).filter(
        Conversation.role == "assistant",
        Conversation.created_at >= since,
        Conversation.compliance_result.isnot(None),
        not_prep_session(Conversation.session_id),
    ).all()

    counts = {}
    for sid, cr in rows:
        if isinstance(cr, dict) and cr.get("blocked"):
            counts[sid] = counts.get(sid, 0) + 1

    high_ids = [sid for sid, cnt in counts.items() if cnt >= REVIEW_BLOCK_THRESHOLD]
    if not high_ids:
        return success({
            "items": [], "threshold": REVIEW_BLOCK_THRESHOLD, "window_hours": REVIEW_WINDOW_HOURS,
        })

    specialists = db.query(Specialist).filter(Specialist.id.in_(high_ids)).all()
    spec_by_id = {s.id: s for s in specialists}
    rep_ids = [s.representative_id for s in specialists if s.representative_id]
    rep_name_map = {}
    if rep_ids:
        rep_name_map = {
            uid: name
            for uid, name in db.query(User.id, User.full_name).filter(User.id.in_(rep_ids)).all()
        }

    items = []
    for sid in sorted(high_ids, key=lambda x: counts[x], reverse=True):
        s = spec_by_id.get(sid)
        items.append({
            "specialist_id": sid,
            "name": s.name if s else "未知分身",
            "rep_name": rep_name_map.get(s.representative_id) if (s and s.representative_id) else None,
            "block_count": counts[sid],
            "window_hours": REVIEW_WINDOW_HOURS,
            "threshold": REVIEW_BLOCK_THRESHOLD,
        })
    return success({
        "items": items, "threshold": REVIEW_BLOCK_THRESHOLD, "window_hours": REVIEW_WINDOW_HOURS,
    })


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
                          question: str, result: dict, persist_session_id=None):
    """落库问答两行，返回 assistant 行 id（反馈/收藏的主键）。

    persist_session_id：显式覆盖落库 session_id —— visit-service 的 prep 调用
    传入 visit_prep_ 前缀会话，百炼可能回自己的 dialog_id 覆盖掉前缀，须钉住
    原始标记否则 specialist 侧的过滤失效。
    入库失败不影响 chat 主流程 —— 返回 None，前端据此禁用反馈/收藏。
    """
    from app.models.conversation import Conversation
    session_id = persist_session_id or result.get("session_id")
    try:
        conv = Conversation(
            user_id=user_id,
            specialist_id=specialist_id,
            session_id=session_id,
            role="user",
            content=question,
        )
        db.add(conv)
        conv_ai = Conversation(
            user_id=user_id,
            specialist_id=specialist_id,
            session_id=session_id,
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

    # 一期 B 挂账收尾：doctor 角色必须先订阅该分身（未订阅不可 chat）
    if current_user["role"] == "doctor":
        from shared.models.doctor import DoctorTwinSubscription
        sub = db.query(DoctorTwinSubscription).filter(
            DoctorTwinSubscription.doctor_id == current_user["id"],
            DoctorTwinSubscription.twin_id == specialist_id,
            DoctorTwinSubscription.status == "subscribed",
        ).first()
        if not sub:
            raise PermissionError("请先添加该分身再对话")

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

    # 调用答案生成器（D5：传 db —— 降级时取同 session 最近几轮问答拼多轮上下文）
    generator = AnswerGenerator()
    result = await generator.generate(
        question=question,
        specialist=specialist,
        user_id=current_user["id"],
        session_id=session_id,
        db=db,
    )

    # 对话记录入库 —— conversation_id 是前端反馈/收藏的主键
    # prep 调用（visit_prep_ 前缀）钉住原始 session 落库，防百炼 dialog_id 覆盖标记
    persist_sid = session_id if (session_id or "").startswith(VISIT_PREP_SESSION_PREFIX) else None
    result["conversation_id"] = _persist_conversation(
        db, current_user["id"], specialist_id, question, result, persist_session_id=persist_sid
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
    # 每轮对话落库 user+assistant 两行 —— 只按 role='user' 计数避免双倍；
    # 排除 visit_prep_ 机器会话（拜访准备指令非真人提问）
    total = db.query(func.count(Conversation.id)).filter(
        Conversation.specialist_id == specialist_id,
        Conversation.role == "user",
        not_prep_session(Conversation.session_id),
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
    "is_official", "representative_id",
}
VALID_STATUSES = {"draft", "active", "disabled", "frozen"}


def _normalize_status(status: str) -> str:
    s = (status or "").strip().lower()
    if s not in VALID_STATUSES:
        raise ParamError(f"status 必须是 {'/'.join(sorted(VALID_STATUSES))}")
    return s


def _validate_specialist_fields(request: dict, creating: bool, existing: dict = None) -> dict:
    """白名单 + 必填校验（纯函数，便于单测）。

    creating 与 updating 都接受 SPECIALIST_UPDATE_FIELDS 白名单字段，
    白名单之外的字段一律 ParamError；creating 额外要求 name 与 product_id 非空。
    D2（2026-08-13）：
    - name 传了就必须非空（含 update —— name 是 NOT NULL 列，null/空串无法落库）；
    - product_id 传了就必须能转 int（防 create 的 int() 抛 ValueError 变 500）；
      显式 null 放行（update 清空 product_id 引用，可空 FK）。
    L-4（2026-08-24 审查修复）：官方分身不变式按"合并后"状态判定 ——
    existing 传当前行 {is_official, representative_id}，payload 只改其一
    也能查出冲突；此前两键须同时出现在 payload 才触发，partial update 可绕过。
    """
    data = dict(request)
    allowed = set(data.keys()) - SPECIALIST_UPDATE_FIELDS
    if allowed:
        raise ParamError(f"不允许的字段: {sorted(allowed)}")
    if creating:
        # create 必须带非空 name 与 product_id
        if not (data.get("name") or "").strip():
            raise ParamError("name 不能为空")
        if not data.get("product_id"):
            raise ParamError("product_id 不能为空")
    elif "name" in data and not (data.get("name") or "").strip():
        # update 传了 name 就必须非空（name 是 NOT NULL 列，null/空串无法落库）
        raise ParamError("name 不能为空")
    if "product_id" in data and data.get("product_id") is not None:
        try:
            data["product_id"] = int(data["product_id"])
        except (TypeError, ValueError):
            raise ParamError("product_id 必须为整数")
    # L-4：合并既有行后判定 —— partial update（只带其中一个键）不再绕过
    merged = dict(existing or {})
    for key in ("is_official", "representative_id"):
        if key in data:
            merged[key] = data[key]
    if merged.get("is_official") and merged.get("representative_id"):
        raise ParamError("官方公共数字员工不能绑定代表（representative_id 须为空）")
    return data


def _ensure_product_exists(db: Session, product_id: int) -> None:
    """D2（2026-08-13）：product_id 引用的产品必须存在。

    否则提交时撞 products FK 约束变 500 IntegrityError；预检后转业务错误，
    与 auth A2 的 manager_id 存在性预检同思路。
    """
    from shared.models.product import Product
    exists = db.query(Product).filter(Product.id == product_id).first()
    if not exists:
        raise BusinessError(f"产品不存在: {product_id}")


# ==================== 分身冻结/解冻（合规风控，人工裁决） ====================

@router.post("/{specialist_id}/freeze")
async def freeze_specialist(
    specialist_id: int,
    payload: dict,
    current_user: dict = Depends(require_roles("admin", "manager", "compliance")),
    db: Session = Depends(get_db),
):
    """合规冻结分身（需求 3.2(3) 人工裁决）：reason 必填 + 审计。不做自动冻结。"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    reason = (payload.get("reason") or "").strip() if isinstance(payload.get("reason"), str) else ""
    if not reason:
        raise ParamError("冻结必须填写理由")
    spec = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not spec:
        raise BusinessError("分身不存在", code=4000)
    if spec.status == "frozen":
        raise BusinessError("分身已处于冻结状态", code=4001)
    spec.status = "frozen"
    db.commit()
    db.refresh(spec)
    await write_audit_log(
        action="specialist_freeze",
        user_id=current_user["id"],
        resource_type="digital_specialist",
        resource_id=str(spec.id),
        after_value={"status": "frozen", "reason": reason},
        request_id=get_request_id() or None,
    )
    return success(spec.to_dict())


@router.post("/{specialist_id}/unfreeze")
async def unfreeze_specialist(
    specialist_id: int,
    current_user: dict = Depends(require_roles("admin", "manager", "compliance")),
    db: Session = Depends(get_db),
):
    """解冻分身：frozen → active + 审计"""
    spec = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not spec:
        raise BusinessError("分身不存在", code=4000)
    if spec.status != "frozen":
        raise BusinessError("分身未处于冻结状态", code=4001)
    spec.status = "active"
    db.commit()
    db.refresh(spec)
    await write_audit_log(
        action="specialist_unfreeze",
        user_id=current_user["id"],
        resource_type="digital_specialist",
        resource_id=str(spec.id),
        after_value={"status": "active"},
        request_id=get_request_id() or None,
    )
    return success(spec.to_dict())


# ==================== 分身管理（风格设置/启停/风格测试生成） ====================

VALID_STYLE_KEYS = {"formal_level", "reply_length", "opening_mode"}
VALID_FORMAL = ("非常严谨", "标准学术", "略带亲和力")
VALID_LENGTH = ("简洁", "标准", "详尽")
VALID_OPENING = ("直切主题", "先寒暄再进入")


def _validate_style(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    style = {}
    if "formal_level" in payload:
        v = payload["formal_level"]
        if v not in VALID_FORMAL:
            raise ParamError("formal_level 必须是 非常严谨/标准学术/略带亲和力")
        style["formal_level"] = v
    if "reply_length" in payload:
        v = payload["reply_length"]
        if v not in VALID_LENGTH:
            raise ParamError("reply_length 必须是 简洁/标准/详尽")
        style["reply_length"] = v
    if "opening_mode" in payload:
        v = payload["opening_mode"]
        if v not in VALID_OPENING:
            raise ParamError("opening_mode 必须是 直切主题/先寒暄再进入")
        style["opening_mode"] = v
    if not style:
        raise ParamError("至少设置一个风格参数")
    return style


def _assert_twin_owner(spec: Specialist, current_user: dict):
    """分身归属校验：代表本人或 admin/manager（管理端代理操作）"""
    if current_user["role"] in ("admin", "manager"):
        return
    if spec.representative_id != current_user["id"]:
        raise PermissionError("只能操作本人分身")


@router.put("/{specialist_id}/style")
async def set_twin_style(
    specialist_id: int,
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分身风格设置（需求 4.3(2)）：写 persona.style"""
    spec = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not spec:
        raise BusinessError("分身不存在", code=4000)
    _assert_twin_owner(spec, current_user)
    style = _validate_style(payload)
    persona = dict(spec.persona) if spec.persona else {}
    persona["style"] = {**(persona.get("style") or {}), **style}
    spec.persona = persona
    db.commit()
    db.refresh(spec)
    return success(spec.to_dict())


@router.post("/{specialist_id}/pause")
async def pause_twin(
    specialist_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """暂停本人分身（4.3(5)）：status→paused"""
    spec = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not spec:
        raise BusinessError("分身不存在", code=4000)
    _assert_twin_owner(spec, current_user)
    if spec.status != "active":
        raise BusinessError("仅工作中的分身可暂停", code=4001)
    spec.status = "paused"
    db.commit()
    db.refresh(spec)
    return success(spec.to_dict())


@router.post("/{specialist_id}/resume")
async def resume_twin(
    specialist_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """启用本人分身：paused→active"""
    spec = db.query(Specialist).filter(Specialist.id == specialist_id).first()
    if not spec:
        raise BusinessError("分身不存在", code=4000)
    _assert_twin_owner(spec, current_user)
    if spec.status != "paused":
        raise BusinessError("仅已暂停的分身可启用", code=4001)
    spec.status = "active"
    db.commit()
    db.refresh(spec)
    return success(spec.to_dict())


@router.post("/style-test")
async def style_test_generate(
    payload: dict,
    current_user: dict = Depends(require_roles("rep")),
    db: Session = Depends(get_db),
):
    """分身生成（4.3(1)）：风格测试 5 题 → 生成 persona 风格画像 → 建分身（prompt/检索级个性化，非微调）"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    answers = payload.get("answers")
    if not isinstance(answers, list) or len(answers) != 5 or not all(isinstance(a, int) for a in answers):
        raise ParamError("answers 必须是 5 个 0-2 的选项索引数组")
    # 简化映射：均值 → 正式度/长度/开场白（prompt/检索级个性化口径）
    avg = sum(max(0, min(2, a)) for a in answers) / 5
    formal = "非常严谨" if avg < 0.67 else "标准学术" if avg < 1.34 else "略带亲和力"
    length = "简洁" if avg < 0.67 else "标准" if avg < 1.34 else "详尽"
    opening = "直切主题" if avg < 1.0 else "先寒暄再进入"
    persona = {"style": {"formal_level": formal, "reply_length": length, "opening_mode": opening}}
    from app.config import settings as app_settings
    twin = Specialist(
        name=f"{current_user.get('username')}的分身", product_id=None,
        persona=persona, status="active", representative_id=current_user["id"],
        # 演示安全批（2026-09-03）：挂共享官方百炼 App，建完即可对话；
        # 未配置 DEFAULT_TWIN_BAILIAN_APP_ID 时为 None（旧行为，chat 报未配置）
        bailian_app_id=app_settings.DEFAULT_TWIN_BAILIAN_APP_ID or None,
    )
    db.add(twin)
    db.commit()
    db.refresh(twin)
    return success(twin.to_dict())


# ==================== 专员 CRUD（S6：仅 admin） ====================

@router.post("")
async def create_specialist(
    request: dict,
    current_user: dict = Depends(require_roles("admin", "manager", "compliance", "medical")),
    db: Session = Depends(get_db),
):
    """创建专员"""
    data = _validate_specialist_fields(request, creating=True)
    _ensure_product_exists(db, data["product_id"])
    specialist = Specialist(
        name=data["name"].strip(),
        product_id=data["product_id"],
        persona=data.get("persona"),
        knowledge_scope=data.get("knowledge_scope"),
        compliance_level=data.get("compliance_level", "internal"),
        bailian_app_id=data.get("bailian_app_id"),
        status=_normalize_status(data.get("status", "draft")),
        is_official=data.get("is_official", False),
        representative_id=data.get("representative_id"),
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
    data = _validate_specialist_fields(request, creating=False, existing={
        # L-4：partial update 场景下官方分身不变式以合并后状态判定
        "is_official": specialist.is_official,
        "representative_id": specialist.representative_id,
    })
    if "product_id" in data and data["product_id"] is not None:
        _ensure_product_exists(db, data["product_id"])
    for field in SPECIALIST_UPDATE_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if value is None:
            # D2（2026-08-13）：显式 null → 清空字段。旧实现 data[field] is not None
            # 使 persona/knowledge_scope/bailian_app_id/product_id 等可空字段
            # 永远无法清空。name 已被 _validate 拦截（NOT NULL 列）；
            # status 有枚举语义，显式 null 同样按非法值处理。
            if field == "status":
                raise ParamError("status 不能为 null")
            if field == "is_official":
                raise ParamError("is_official 不能为 null")
            setattr(specialist, field, None)
            continue
        value = _normalize_status(value) if field == "status" else value
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
