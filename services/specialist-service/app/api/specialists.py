"""数字专员服务 API 路由"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from shared.common.response import success, ParamError
from shared.common.auth import get_current_user, require_roles
from app.services.audit_client import write_audit_log
from shared.common.db_session import get_db
from app.models.specialist import Specialist
from app.core.answer_generator import AnswerGenerator

router = APIRouter(prefix="/api/v1/specialists", tags=["specialists"])
logger = logging.getLogger(__name__)


# ==================== 专员列表 & 详情 ====================

@router.get("")
async def list_specialists(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """专员列表"""
    specialists = db.query(Specialist).filter(
        Specialist.status == "active"
    ).all()
    return success([s.to_dict() for s in specialists])


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

    # 调用答案生成器
    generator = AnswerGenerator()
    result = await generator.generate(
        question=question,
        specialist=specialist,
        user_id=current_user["id"],
        session_id=session_id,
    )

    # 对话记录入库
    try:
        from app.models.conversation import Conversation
        conv = Conversation(
            user_id=current_user["id"],
            specialist_id=specialist_id,
            session_id=result.get("session_id"),
            role="user",
            content=question,
        )
        db.add(conv)
        conv_ai = Conversation(
            user_id=current_user["id"],
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
    except Exception as e:
        logger.error(f"对话记录入库失败: {e}")

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
    total = db.query(func.count(Conversation.id)).filter(
        Conversation.specialist_id == specialist_id
    ).scalar()
    positive = db.query(func.count(ConversationFeedback.id)).filter(
        ConversationFeedback.specialist_id == specialist_id,
        ConversationFeedback.rating == 1,
    ).scalar()
    negative = db.query(func.count(ConversationFeedback.id)).filter(
        ConversationFeedback.specialist_id == specialist_id,
        ConversationFeedback.rating == -1,
    ).scalar()
    return success({"total_conversations": total, **compute_satisfaction(positive or 0, negative or 0)})


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
    """白名单 + 必填校验（纯函数，便于单测）"""
    allowed = set(request.keys()) - SPECIALIST_UPDATE_FIELDS
    if creating:
        allowed -= {"name"}
        allowed.discard("status")
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
