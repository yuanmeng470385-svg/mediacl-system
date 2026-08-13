"""拜访记录数据访问层"""
import logging
from typing import List, Optional, Tuple, Dict, Iterable
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam, or_
from sqlalchemy.exc import IntegrityError
from shared.common.response import ParamError
from app.models.visit_record import VisitRecord
from app.constants import AI_SUMMARY_PLACEHOLDER, VISIT_STATUS_CANCELLED, VISIT_STATUS_IN_PROGRESS

logger = logging.getLogger(__name__)

# 同库直读 hcps（数据属于 hcp-service，此处只读）—— 批量取医生姓名供列表/详情展示
_HCP_NAMES_SQL = text(
    "SELECT id, name FROM hcps WHERE id IN :ids"
).bindparams(bindparam("ids", expanding=True))


class VisitRepo:
    """拜访记录仓库"""

    @staticmethod
    def get(db: Session, visit_id: int, for_update: bool = False) -> Optional[VisitRecord]:
        """按 id 取拜访记录；for_update=True 时对行加锁并刷新为最新已提交行（防并发读改写丢失更新）"""
        query = db.query(VisitRecord).filter(VisitRecord.id == visit_id)
        if for_update:
            # F2 终审（2026-08-13）：populate_existing —— 不加则 Session 内已缓存的
            # 旧实例（如 _llm_recommend 冷却判断的无锁读）被 identity map 直接返回，
            # 锁内重读名存实亡，LLM 窗口内并发提交的 key_nodes 追加仍会覆盖丢失。
            # populate_existing 仅刷新已在 session 中的对象为最新行，首读无副作用。
            query = query.with_for_update().populate_existing()
        return query.first()

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

        status: in_progress（未生成总结或占位串可重试）/ completed（已结束）/
                cancelled（已取消）。口径与 visit_record.to_dict 一致（B14）：
                占位串不算已结束；取消的记录不进 in_progress/completed。
        """
        query = db.query(VisitRecord)
        if user_id:
            query = query.filter(VisitRecord.user_id == user_id)
        if hcp_id:
            query = query.filter(VisitRecord.hcp_id == hcp_id)
        if product_id:
            query = query.filter(VisitRecord.product_id == product_id)
        if status == VISIT_STATUS_IN_PROGRESS:
            query = query.filter(
                VisitRecord.status != VISIT_STATUS_CANCELLED,
                or_(VisitRecord.ai_summary.is_(None), VisitRecord.ai_summary == AI_SUMMARY_PLACEHOLDER),
            )
        elif status == "completed":
            query = query.filter(
                VisitRecord.status != VISIT_STATUS_CANCELLED,
                VisitRecord.ai_summary.isnot(None),
                VisitRecord.ai_summary != AI_SUMMARY_PLACEHOLDER,
            )
        elif status == VISIT_STATUS_CANCELLED:
            query = query.filter(VisitRecord.status == VISIT_STATUS_CANCELLED)
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
