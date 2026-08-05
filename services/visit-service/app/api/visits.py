"""陪访助手服务 API 路由"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from shared.common.response import success, ParamError
from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from app.models.visit_record import VisitRecord
from app.db.repositories.visit_repo import VisitRepo
from app.core.visit_manager import VisitManager

router = APIRouter(prefix="/api/v1/visits", tags=["visits"])
logger = logging.getLogger(__name__)

_visit_manager = VisitManager()


def _auth_token(raw_request: Request) -> Optional[str]:
    """从请求头提取用户 JWT —— 透传给 specialist chat（网关要求 JWT，不带则 401）"""
    header = raw_request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def _get_visit_or_404(db: Session, visit_id: int) -> VisitRecord:
    record = VisitRepo.get(db, visit_id)
    if not record:
        raise HTTPException(status_code=404, detail="拜访记录不存在")
    return record


def _assert_visit_owner(db: Session, visit_id: int, current_user: dict) -> VisitRecord:
    """归属校验（S4）：拜访记录只能被本人操作；admin 例外。返回记录本身。"""
    record = _get_visit_or_404(db, visit_id)
    if record.user_id != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权操作该拜访记录")
    return record


# PUT 允许编辑的业务字段白名单（S4）：
# AI 生成字段（ai_summary/transcript/compliance_flags 等）与归属字段
# （user_id/id）不允许通过普通编辑接口修改 —— 拜访记录是监管取证证据。
ALLOWED_UPDATE_FIELDS = {
    "hcp_id", "product_id", "specialist_id",
    "visit_time", "duration_minutes", "attachments",
}


# ==================== 拜访前 ====================

@router.post("/pre-visit")
async def pre_visit(
    request: dict,
    raw_request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """拜访前准备包：医生画像 + 历史互动 → AI 生成推荐话题/红线提醒/开场白

    Request: {"hcp_id": 1, "product_id": 1}
    """
    hcp_id = request.get("hcp_id")
    product_id = request.get("product_id")
    if not hcp_id:
        raise ParamError("hcp_id 不能为空")
    if not product_id:
        raise ParamError("product_id 不能为空")
    result = await _visit_manager.prepare_visit(
        db, hcp_id=int(hcp_id), user_id=current_user["id"], product_id=int(product_id),
        auth_token=_auth_token(raw_request),
    )
    return success(result)


# ==================== 拜访中 ====================

@router.post("/start")
async def start_visit(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """开始拜访：创建拜访记录

    Request: {"hcp_id": 1, "product_id": 1}
    """
    hcp_id = request.get("hcp_id")
    product_id = request.get("product_id")
    if not hcp_id:
        raise ParamError("hcp_id 不能为空")
    if not product_id:
        raise ParamError("product_id 不能为空")
    result = await _visit_manager.start_visit(
        db, hcp_id=int(hcp_id), user_id=current_user["id"], product_id=int(product_id)
    )
    return success(result)


@router.post("/{visit_id}/transcript")
async def process_transcript(
    visit_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """处理拜访中对话：ASR 转写 + 合规实时检查 + 异议识别

    Request: {"audio_url": "https://oss/audio.wav"} 或 {"text": "直接文本内容"}
    """
    _assert_visit_owner(db, visit_id, current_user)
    audio_url = request.get("audio_url")
    text_content = request.get("text")
    if not audio_url and not text_content:
        raise ParamError("audio_url 和 text 至少提供一个")
    result = await _visit_manager.process_transcript(
        db, visit_id, current_user["id"],
        audio_url=audio_url, text_content=text_content,
    )
    return success(result)


# ==================== 拜访后 ====================

@router.post("/{visit_id}/end")
async def end_visit(
    visit_id: int,
    request: dict,
    raw_request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """结束拜访：AI 生成结构化记录（摘要/关键点/兴趣点/异议/情感/下次计划）

    Request: {"full_transcript": "可选，完整对话文本，不传则用已累积的转写"}
    """
    _assert_visit_owner(db, visit_id, current_user)
    result = await _visit_manager.end_visit(
        db, visit_id, current_user["id"],
        full_transcript=request.get("full_transcript"),
        auth_token=_auth_token(raw_request),
    )
    return success(result)


@router.post("/{visit_id}/follow-up")
async def follow_up(
    visit_id: int,
    raw_request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """跟进建议：基于拜访记录 + 医生信息 → AI 生成跟进计划"""
    _assert_visit_owner(db, visit_id, current_user)
    result = await _visit_manager.follow_up(
        db, visit_id, current_user["id"], auth_token=_auth_token(raw_request)
    )
    return success(result)


# ==================== 列表 & 详情 & 编辑 ====================

@router.get("/{visit_id}")
async def get_visit(
    visit_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """拜访详情"""
    record = _assert_visit_owner(db, visit_id, current_user)
    return success(record.to_dict())


@router.get("")
async def list_visits(
    page: int = 1,
    page_size: int = 20,
    user_id: Optional[int] = None,
    hcp_id: Optional[int] = None,
    product_id: Optional[int] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """拜访列表（分页 + 筛选）

    status: in_progress（未生成总结）/ completed（已结束）
    """
    # S4：非 admin 不能按 user_id 筛全公司记录 —— 强制只看自己的
    if current_user.get("role") != "admin":
        user_id = current_user["id"]
    p = PaginationParams(page=page, page_size=page_size)
    items, total = VisitRepo.list(
        db, page=p.page, page_size=p.page_size,
        user_id=user_id, hcp_id=hcp_id, product_id=product_id,
        status=status, date_from=date_from, date_to=date_to,
    )
    return success(paginate([i.to_dict() for i in items], total, p.page, p.page_size))


@router.put("/{visit_id}")
async def update_visit(
    visit_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑拜访记录（仅更新白名单内的业务字段）"""
    record = _assert_visit_owner(db, visit_id, current_user)
    # 字段白名单（S4）：AI 生成/合规证据/归属字段一律拒绝 —— 不再任意 setattr
    allowed = {k: v for k, v in request.items() if k in ALLOWED_UPDATE_FIELDS and v is not None}
    record = VisitRepo.update(db, record, allowed)
    return success(record.to_dict())
