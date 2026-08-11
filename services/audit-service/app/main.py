"""审计服务 - FastAPI 入口"""
import asyncio
import sys
import os
from contextlib import asynccontextmanager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import settings

# 审计服务强制使用专用低权账号（AUDIT_DATABASE_URL，见 002_audit_immutable.sql）。
# shared/common/db_session.py 在 import 时读 DATABASE_URL，这里必须在挂载路由前覆盖，
# 否则审计服务会用 medagent 账号连接、从而绕过 REVOKE 约束。
os.environ["DATABASE_URL"] = settings.DATABASE_URL

from shared.common.exception_handler import register_exception_handlers
from shared.common.request_id_middleware import RequestIDMiddleware

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def _cleanup_loop() -> None:
    """审计日志保留天数清理（AUDIT_LOG_RETENTION_DAYS 生效，2026-08-11）：
    启动即跑一次，此后按 AUDIT_LOG_CLEANUP_INTERVAL_HOURS 周期执行。
    同步 DB 删除丢线程池（asyncio.to_thread），不阻塞事件循环。
    多 worker 部署时各进程各跑一份——DELETE 幂等（同一批数据先删的生效），
    多余的一次扫描可接受；权限不足（未配清理账号）记 error 日志，不崩。
    """
    from app.core.cleanup import run_cleanup_once

    logger.info(
        "审计日志清理任务启动：保留 %s 天，每 %s 小时执行一次",
        settings.AUDIT_LOG_RETENTION_DAYS, settings.AUDIT_LOG_CLEANUP_INTERVAL_HOURS,
    )
    while True:
        try:
            await asyncio.to_thread(run_cleanup_once)
        except Exception as exc:
            logger.error(
                "审计日志清理失败（检查 AUDIT_CLEANUP_DATABASE_URL 是否配置 "
                "medagent_audit_cleanup 维护账号，见 migrations/005_audit_cleanup.sql）: %s",
                exc,
            )
        await asyncio.sleep(settings.AUDIT_LOG_CLEANUP_INTERVAL_HOURS * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="MedAgent - 审计服务",
    description="不可篡改审计日志、高级搜索、监管报告导出",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# X-Request-ID 链路（需求 7.1）：从请求头读取网关透传的 ID 写入 context，
# 审计日志落库 request_id 取用；无头时生成（服务直连场景兜底）
app.add_middleware(RequestIDMiddleware)

# 注册全局异常处理器
register_exception_handlers(app)

# 挂载路由
from app.api.logs import router as logs_router
app.include_router(logs_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.SERVICE_PORT)
