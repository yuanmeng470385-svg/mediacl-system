"""拜访记录数据访问层"""
import logging
from typing import List, Optional, Tuple, Dict
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.visit_record import VisitRecord

logger = logging.getLogger(__name__)


class VisitRepo:
    """拜访记录仓库"""

    @staticmethod
    def get(db: Session, visit_id: int) -> Optional[VisitRecord]:
        return db.query(VisitRecord).filter(VisitRecord.id == visit_id).first()

    @staticmethod
    def list(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        user_id: Optional[int] = None,
        hcp_id: Optional[int] = None,
        product_id: Optional[int] = None,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Tuple[List[VisitRecord], int]:
        """分页列表 + 筛选

        status: in_progress（未生成总结）/ completed（已结束）
        """
        query = db.query(VisitRecord)
        if user_id:
            query = query.filter(VisitRecord.user_id == user_id)
        if hcp_id:
            query = query.filter(VisitRecord.hcp_id == hcp_id)
        if product_id:
            query = query.filter(VisitRecord.product_id == product_id)
        if status == "in_progress":
            query = query.filter(VisitRecord.ai_summary.is_(None))
        elif status == "completed":
            query = query.filter(VisitRecord.ai_summary.isnot(None))
        if date_from:
            query = query.filter(VisitRecord.visit_time >= datetime.fromisoformat(date_from))
        if date_to:
            query = query.filter(VisitRecord.visit_time <= datetime.fromisoformat(date_to))

        total = query.count()
        items = query.order_by(VisitRecord.visit_time.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()
        return items, total

    @staticmethod
    def create(db: Session, data: Dict) -> VisitRecord:
        record = VisitRecord(**data)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def update(db: Session, record: VisitRecord, data: Dict) -> VisitRecord:
        for key, value in data.items():
            if hasattr(record, key) and value is not None:
                setattr(record, key, value)
        db.commit()
        db.refresh(record)
        return record
