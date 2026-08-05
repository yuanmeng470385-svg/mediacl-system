"""数字专员服务 API 路由"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from shared.common.response import success, ParamError
from shared.common.auth import get_current_user
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
