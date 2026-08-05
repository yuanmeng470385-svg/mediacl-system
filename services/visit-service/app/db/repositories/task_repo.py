"""任务数据访问层"""
import logging
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.task import Task

logger = logging.getLogger(__name__)

# channel → task_type 映射（follow_up_items 落库时用）
CHANNEL_TYPE_MAP = {
    "下次拜访": "book_appointment",
    "邮件": "email",
    "电话": "call",
    "微信": "send_material",
}


class TaskRepo:
    @staticmethod
    def create(db: Session, visit_id: int, user_id: int, item: dict) -> Task:
        task = Task(
            visit_id=visit_id,
            user_id=user_id,
            title=item["title"][:500],
            description=item.get("description"),
            task_type=item.get("task_type", "follow_up"),
            due_date=item.get("due_date"),
            channel=item.get("channel"),
            status="open",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def get(db: Session, task_id: int) -> Optional[Task]:
        return db.query(Task).filter(Task.id == task_id).first()

    @staticmethod
    def list_by_user(
        db: Session, user_id: int, status: Optional[str] = None,
        page: int = 1, page_size: int = 20,
    ) -> Tuple[List[Task], int]:
        q = db.query(Task).filter(Task.user_id == user_id)
        if status:
            q = q.filter(Task.status == status)
        total = q.count()
        items = q.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    @staticmethod
    def list_by_visit(db: Session, visit_id: int) -> List[Task]:
        return db.query(Task).filter(Task.visit_id == visit_id).order_by(Task.created_at).all()

    @staticmethod
    def update_status(db: Session, task: Task, status: str) -> Task:
        task.status = status
        db.commit()
        db.refresh(task)
        return task
