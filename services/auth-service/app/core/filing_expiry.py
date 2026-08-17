"""备案到期自动冻结（需求文档 3.3(2)）：每日扫描 filing_expire_date < 今天的代表，
将账号置为 disabled（冻结）。备案状态是确定性事实，无需人工确认。

冻结范围仅 role='rep' 且 status='active'（管理员/合规/医学不冻结）。
多 worker 部署各进程各跑一份——UPDATE 幂等（status 过滤），可接受。
"""
import asyncio
import logging
from datetime import date
from typing import List

from sqlalchemy.orm import Session

from shared.common.db_session import SessionLocal
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)


def freeze_expired_qualifications(db: Session) -> List[User]:
    """同步扫描并冻结到期代表（测试直接调用本函数，不碰 httpx/审计）。"""
    today = date.today()
    rows = (
        db.query(RepresentativeQualification, User)
        .join(User, User.id == RepresentativeQualification.representative_id)
        .filter(
            User.role == "rep",
            User.status == "active",
            RepresentativeQualification.filing_expire_date.isnot(None),
            RepresentativeQualification.filing_expire_date < today,
        )
        .all()
    )
    frozen: List[User] = []
    for _qual, user in rows:
        user.status = "disabled"
        frozen.append(user)
    if frozen:
        db.commit()
    return frozen


async def run_filing_expiry_scan() -> dict:
    """开新会话扫描冻结 + 逐用户写审计（审计失败不阻断冻结结果）。"""
    db = SessionLocal()
    try:
        frozen = await asyncio.to_thread(freeze_expired_qualifications, db)
        for user in frozen:
            await write_audit_log(
                action="qualification_expired_freeze",
                user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                after_value={"reason": "备案到期自动冻结", "freeze_date": date.today().isoformat()},
            )
        if frozen:
            logger.info("备案到期扫描：冻结 %s 个代表账号", len(frozen))
        return {"frozen": len(frozen), "scanned_at": date.today().isoformat()}
    finally:
        db.close()
