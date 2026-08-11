"""审计日志保留天数清理 —— AUDIT_LOG_RETENTION_DAYS 生效实现（2026-08-11）

背景：该配置此前是死配置（只定义从未被消费），审计日志只增不删（含 JSONB 大字段，
3 年默认保留）。本模块由 main.py 的 lifespan 后台任务调用，按配置周期清理。

权限模型（与 002_audit_immutable.sql 不可篡改设计共存）：
- 应用账号 medagent_audit 仍只有 INSERT/SELECT，无权删除（不可篡改语义不变）；
- 删除能力单独授予专职维护账号 medagent_audit_cleanup（仅 SELECT+DELETE，
  migrations/005_audit_cleanup.sql），经独立连接 AUDIT_CLEANUP_DATABASE_URL 使用；
- 未配置维护账号时清理会记录 error 日志（不再静默），服务不崩。
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_DEFAULT_BATCH = 5000


def cleanup_expired_logs(db, retention_days: int, batch: int = _DEFAULT_BATCH) -> dict:
    """分批删除超过保留天数的审计日志（naive UTC：timestamp < utcnow - days）。

    按 id 排序 LIMIT batch 循环删除，避免单条长事务 DELETE 锁住 audit_logs
    （idx_audit_timestamp 支撑范围条件）。返回 {deleted, batches, cutoff}。
    """
    from sqlalchemy import text

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    deleted = 0
    batches = 0
    while True:
        result = db.execute(
            text(
                "DELETE FROM audit_logs WHERE id IN ("
                "  SELECT id FROM audit_logs WHERE timestamp < :cutoff ORDER BY id LIMIT :batch"
                ")"
            ),
            {"cutoff": cutoff, "batch": batch},
        )
        n = result.rowcount
        db.commit()
        deleted += n
        batches += 1
        if n < batch:
            break
    return {"deleted": deleted, "batches": batches, "cutoff": str(cutoff)}


def run_cleanup_once() -> dict:
    """用清理专用连接执行一次清理（AUDIT_CLEANUP_DATABASE_URL）。

    权限不足（未配置 medagent_audit_cleanup）时抛异常，由调用方（lifespan 任务）
    捕获记 error 日志——清理失败必须可观测，不静默。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import settings

    engine = create_engine(settings.CLEANUP_DATABASE_URL, pool_pre_ping=True)
    try:
        session = sessionmaker(bind=engine)()
        try:
            result = cleanup_expired_logs(session, settings.AUDIT_LOG_RETENTION_DAYS)
            logger.info("审计日志清理完成: 删除 %s 行（%s 批，cutoff=%s）",
                        result["deleted"], result["batches"], result["cutoff"])
            return result
        finally:
            session.close()
    finally:
        engine.dispose()
