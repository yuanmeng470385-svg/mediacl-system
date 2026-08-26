"""陪访助手服务 API 路由"""
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from shared.common.response import success, ParamError, BusinessError
from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from app.models.visit_record import VisitRecord
from app.db.repositories.visit_repo import VisitRepo
from app.core.visit_manager import VisitManager
from app.services.audit_client import write_audit_log
from app.constants import (
    AI_SUMMARY_PLACEHOLDER,
    VISIT_STATUS_CANCELLED,
    VISIT_STATUS_COMPLETED,
    VISIT_STATUS_IN_PROGRESS,
)

router = APIRouter(prefix="/api/v1/visits", tags=["visits"])
logger = logging.getLogger(__name__)

_visit_manager = VisitManager()


def _auth_token(raw_request: Request) -> Optional[str]:
    """从请求头提取用户 JWT —— 透传给 specialist chat（网关要求 JWT，不带则 401）"""
    header = raw_request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return header[7:]
    return None


def _to_int_param(value, field_name: str) -> int:
    """请求参数转 int，非法输入抛 ParamError(1000) 而非 500"""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ParamError(f"{field_name} 必须是整数")


def _body_as_dict(payload, endpoint: str) -> dict:
    """请求体必须是 JSON 对象（B15：FastAPI 的 dict 注解不强制类型 ——
    传数组/字符串/数字会 500，显式校验返回 400）"""
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")
    return payload


def _attach_hcp_name(db: Session, record: dict) -> dict:
    """给单条记录 dict 附上 hcp_name（hcps 表只读直查）"""
    hcp_id = record.get("hcp_id")
    record["hcp_name"] = VisitRepo.hcp_names(db, [hcp_id]).get(hcp_id) if hcp_id else None
    return record


def _attach_hcp_names(db: Session, items: List[dict]) -> List[dict]:
    """批量给记录 dict 附上 hcp_name —— 一次查全部相关医生，避免 N+1"""
    ids = {it.get("hcp_id") for it in items if it.get("hcp_id")}
    names = VisitRepo.hcp_names(db, ids)
    for it in items:
        it["hcp_name"] = names.get(it.get("hcp_id"))
    return items


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
    request = _body_as_dict(request, "pre-visit")
    hcp_id = request.get("hcp_id")
    product_id = request.get("product_id")
    if not hcp_id:
        raise ParamError("hcp_id 不能为空")
    if not product_id:
        raise ParamError("product_id 不能为空")
    result = await _visit_manager.prepare_visit(
        db, hcp_id=_to_int_param(hcp_id, "hcp_id"), user_id=current_user["id"],
        product_id=_to_int_param(product_id, "product_id"),
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
    request = _body_as_dict(request, "start")
    hcp_id = request.get("hcp_id")
    product_id = request.get("product_id")
    if not hcp_id:
        raise ParamError("hcp_id 不能为空")
    if not product_id:
        raise ParamError("product_id 不能为空")
    result = await _visit_manager.start_visit(
        db, hcp_id=_to_int_param(hcp_id, "hcp_id"), user_id=current_user["id"],
        product_id=_to_int_param(product_id, "product_id"),
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
    request = _body_as_dict(request, "transcript")
    audio_url = request.get("audio_url")
    text_content = request.get("text")
    if audio_url is not None and not isinstance(audio_url, str):
        raise ParamError("audio_url 必须是字符串")
    if text_content is not None and not isinstance(text_content, str):
        raise ParamError("text 必须是字符串")
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
    raw_request: Request,
    request: dict | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """结束拜访：AI 生成结构化记录（摘要/关键点/兴趣点/异议/情感/下次计划）

    Request: {"full_transcript": "可选，完整对话文本，不传则用已累积的转写"}
    说明：body 整体可选——移动端 endVisit 不带 body（真机联调 422：必填 dict 被 FastAPI
    校验层拒绝，full_transcript 本身就是可选契约，body 不应是必填）。
    """
    _assert_visit_owner(db, visit_id, current_user)
    if request is not None and not isinstance(request, dict):
        raise ParamError("请求体必须是 JSON 对象")
    full_transcript = (request or {}).get("full_transcript")
    # B6（2026-08-13）：full_transcript 非字符串（数字/数组等）→ 400，不进 manager
    # 拼接 prompt（旧实现会把垃圾拼进转写证据，或在下游 500）
    if full_transcript is not None and not isinstance(full_transcript, str):
        raise ParamError("full_transcript 必须是字符串")
    result = await _visit_manager.end_visit(
        db, visit_id, current_user["id"],
        full_transcript=full_transcript,
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


@router.post("/{visit_id}/cancel")
async def cancel_visit(
    visit_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消拜访（B3 修复）：仅进行中的拜访可取消 —— 移动端误开/拜访未进行的
    显式出口，不再只能等 end。证据安全：取消后不能再追加转写 / 结束 / 跟进
    （visit_manager 与 asr_ws 均检查 status），取消本身留审计日志。
    """
    _assert_visit_owner(db, visit_id, current_user)
    # 行锁复查：owner 检查（无锁读）与加锁之间状态可能已变（并发 end），
    # 锁内二次校验保证"进行中 → 取消"判定与 end/transcript 串行化
    record = VisitRepo.get(db, visit_id, for_update=True)
    if not record:
        raise HTTPException(status_code=404, detail="拜访记录不存在")
    if record.status == VISIT_STATUS_CANCELLED:
        raise BusinessError("拜访已取消，无需重复取消", code=4001)
    if record.ai_summary and record.ai_summary != AI_SUMMARY_PLACEHOLDER:
        raise BusinessError("拜访已结束，不能取消", code=4001)

    record.status = VISIT_STATUS_CANCELLED
    db.commit()
    logger.info("拜访取消: visit_id=%s user_id=%s", visit_id, current_user["id"])
    await write_audit_log(
        user_id=current_user["id"], action="visit_cancel",
        resource_type="visit", resource_id=str(visit_id),
    )
    result = record.to_dict()
    result["visit_id"] = record.id  # 移动端契约：读取 visit_id
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
    return success(_attach_hcp_name(db, record.to_dict()))


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

    status: in_progress（未生成总结）/ completed（已结束）/ cancelled（已取消）
    """
    # B3（2026-08-13）：status 白名单 —— 非法值直接 400，不再静默忽略返回全量
    # （静默忽略掩盖客户端 bug，且接口文档承诺了筛选语义）
    if status is not None and status not in (
        VISIT_STATUS_IN_PROGRESS, VISIT_STATUS_COMPLETED, VISIT_STATUS_CANCELLED,
    ):
        raise ParamError("status 必须是 in_progress/completed/cancelled")
    # S4：非 admin 不能按 user_id 筛全公司记录 —— 强制只看自己的
    if current_user.get("role") != "admin":
        user_id = current_user["id"]
    p = PaginationParams(page=page, page_size=page_size)
    items, total = VisitRepo.list(
        db, page=p.page, page_size=p.page_size,
        user_id=user_id, hcp_id=hcp_id, product_id=product_id,
        status=status, date_from=date_from, date_to=date_to,
    )
    records = _attach_hcp_names(db, [i.to_dict() for i in items])
    return success(paginate(records, total, p.page, p.page_size))


@router.put("/{visit_id}")
async def update_visit(
    visit_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑拜访记录（仅更新白名单内的业务字段）"""
    record = _assert_visit_owner(db, visit_id, current_user)
    request = _body_as_dict(request, "update")
    # 字段白名单（S4）：AI 生成/合规证据/归属字段一律拒绝 —— 不再任意 setattr
    allowed = {k: v for k, v in request.items() if k in ALLOWED_UPDATE_FIELDS and v is not None}
    record = VisitRepo.update(db, record, allowed)
    return success(record.to_dict())
