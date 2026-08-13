"""拜访任务接口"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.pagination import PaginationParams, paginate
from shared.common.response import ParamError, success

from app.db.repositories.task_repo import TaskRepo

router = APIRouter(prefix="/api/v1", tags=["tasks"])
logger = logging.getLogger(__name__)

TASK_STATUSES = {"open", "done", "cancelled"}


def _get_task_or_404(db: Session, task_id: int):
    task = TaskRepo.get(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


def _assert_task_owner(task, current_user: dict):
    if task.user_id != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="无权操作该任务")


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """我的任务列表"""
    # B3（2026-08-13）：status 白名单（与 update 同一 TASK_STATUSES）——
    # 非法值直接 400，不再静默忽略返回全量
    if status is not None and status not in TASK_STATUSES:
        raise ParamError(f"status 必须是 {'/'.join(sorted(TASK_STATUSES))}")
    p = PaginationParams(page=page, page_size=page_size)
    items, total = TaskRepo.list_by_user(
        db, current_user["id"], status=status, page=p.page, page_size=p.page_size,
    )
    return success(paginate([t.to_dict() for t in items], total=total, page=p.page, page_size=p.page_size))


@router.put("/tasks/{task_id}")
async def update_task_status(
    task_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """完成任务/取消：{"status": "done"|"cancelled"|"open"}"""
    task = _get_task_or_404(db, task_id)
    _assert_task_owner(task, current_user)
    status = (request.get("status") or "").strip().lower()
    if status not in TASK_STATUSES:
        raise ParamError(f"status 必须是 {'/'.join(sorted(TASK_STATUSES))}")
    task = TaskRepo.update_status(db, task, status)
    return success(task.to_dict())


@router.get("/visits/{visit_id}/tasks")
async def list_visit_tasks(
    visit_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """某次拜访的任务（归属校验：拜访本人或 admin）"""
    from app.api.visits import _assert_visit_owner
    _assert_visit_owner(db, visit_id, current_user)
    tasks = TaskRepo.list_by_visit(db, visit_id)
    return success([t.to_dict() for t in tasks])
