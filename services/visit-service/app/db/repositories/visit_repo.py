"""拜访记录数据访问层"""
import logging
from typing import List, Optional, Tuple, Dict, Iterable
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam
from sqlalchemy.exc import IntegrityError
from shared.common.response import ParamError
from app.models.visit_record import VisitRecord

logger = logging.getLogger(__name__)

# 同库直读 hcps（数据属于 hcp-service，此处只读）—— 批量取医生姓名供列表/详情展示
_HCP_NAMES_SQL = text(
    "SELECT id, name FROM hcps WHERE id IN :ids"
).bindparams(bindparam("ids", expanding=True))


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
            try:
                date_from_dt = datetime.fromisoformat(date_from)
            except ValueError:
                raise ParamError("date_from 格式不正确（应为 ISO 日期时间）")
            query = query.filter(VisitRecord.visit_time >= date_from_dt)
        if date_to:
            try:
                date_to_dt = datetime.fromisoformat(date_to)
            except ValueError:
                raise ParamError("date_to 格式不正确（应为 ISO 日期时间）")
            query = query.filter(VisitRecord.visit_time <= date_to_dt)

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
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()  # 恢复 session 可用状态，避免后续请求复用损坏的会话
            logger.warning("拜访记录更新外键冲突: %s", exc)
            raise ParamError("更新失败：外键引用不存在（hcp_id/product_id 无效）")
        db.refresh(record)
        return record

    @staticmethod
    def hcp_names(db: Session, hcp_ids: Iterable[int]) -> Dict[int, str]:
        """批量查医生姓名（hcps 表只读直查）—— 一次查出所有相关 hcp 名字，避免 N+1"""
        ids = [i for i in set(hcp_ids or []) if i]
        if not ids:
            return {}
        try:
            rows = db.execute(_HCP_NAMES_SQL, {"ids": ids}).mappings().all()
            return {r["id"]: r["name"] for r in rows}
        except Exception as exc:
            logger.warning("读取医生姓名失败（不影响列表）: %s", exc)
            return {}
