"""互动历史只读查询 — 读取 visit-service 的 visit_records 表（同库直读，不跨服务调用）"""
import logging
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# 只读 visit_records 的关键字段，避免与 visit-service 的模型定义重复
_INTERACTION_SQL = text("""
    SELECT id, visit_time, duration_minutes, sentiment, ai_summary,
           key_points, hcp_interests, hcp_objections,
           follow_up_suggestions, next_visit_plan
    FROM visit_records
    WHERE hcp_id = :hcp_id
    ORDER BY visit_time DESC
    LIMIT :limit
""")


def list_interactions(db: Session, hcp_id: int, limit: int = 20) -> List[Dict]:
    """查询某医生的最近互动记录（按拜访时间倒序）"""
    try:
        rows = db.execute(_INTERACTION_SQL, {"hcp_id": hcp_id, "limit": limit}).mappings().all()
        return [
            {
                "id": r["id"],
                "visit_time": r["visit_time"].isoformat() if r["visit_time"] else None,
                "duration_minutes": r["duration_minutes"],
                "sentiment": r["sentiment"],
                "ai_summary": r["ai_summary"],
                "key_points": r["key_points"],
                "interests": r["hcp_interests"],
                "objections": r["hcp_objections"],
                "follow_up_suggestions": r["follow_up_suggestions"],
                "next_visit_plan": r["next_visit_plan"],
            }
            for r in rows
        ]
    except Exception as e:
        # visit_records 表不存在（visit-service 未建）时降级为空列表，不阻塞画像
        logger.warning(f"查询互动历史失败（hcp_id={hcp_id}）: {e}")
        return []
