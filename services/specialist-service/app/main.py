"""数字学术专员服务 - FastAPI 入口"""
import sys
import os
import asyncio
from contextlib import asynccontextmanager

# 确保 shared 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import settings
from shared.common.exception_handler import register_exception_handlers
from shared.common.request_id_middleware import RequestIDMiddleware

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def _briefing_loop() -> None:
    """夜间简报定时任务（需求 C）：启动即跑一次，此后按
    NIGHTLY_BRIEFING_INTERVAL_HOURS 周期执行。同步 DB 生成丢线程池（to_thread），
    不阻塞事件循环；异常记 error 不崩（多 worker 各跑一份，生成逻辑单行捕获
    唯一键冲突转更新，等效 upsert 幂等）。
    """
    from app.core.briefing_generator import run_briefing_scan

    while True:
        try:
            await run_briefing_scan()
        except Exception as exc:
            logger.error("夜间简报生成失败: %s", exc)
        await asyncio.sleep(settings.NIGHTLY_BRIEFING_INTERVAL_HOURS * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_briefing_loop())
    try:
        yield
    finally:
        task.cancel()


# H1（2026-08-11）：JWT_SECRET fail-fast（同 gateway/auth 守卫）——漏配或弱值
# 拒绝启动，防止 shared 验签回退到公开默认密钥后任何人可伪造任意角色 token 直连
from shared.common.auth import validate_jwt_secret

validate_jwt_secret(settings.JWT_SECRET)

app = FastAPI(
    title="MedAgent - 数字学术专员服务",
    description="管理 AI 数字专员，处理学术问答对话",
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
# 服务内 logger/审计 get_request_id() 取用；无头时生成（服务直连场景兜底）
app.add_middleware(RequestIDMiddleware)

# http_requests_total 计数（REQUESTS 接线）：网关无 /metrics 端点，
# 计数落在核心流量服务的请求中间件（OPTIONS/WS 不计）
from app.core.metrics_middleware import MetricsMiddleware

app.add_middleware(MetricsMiddleware)

# 注册全局异常处理器
register_exception_handlers(app)

# 挂载路由
from app.api.specialists import router as specialists_router
from app.api import conversations
app.include_router(specialists_router)
app.include_router(conversations.router)
app.include_router(conversations.favorites_router)

from app.api import metrics as metrics_api
app.include_router(metrics_api.router)

from app.api.chat_ws import router as chat_ws_router
app.include_router(chat_ws_router)

from app.api.medical import router as medical_router
app.include_router(medical_router)

from app.api.twin_subscriptions import router as twin_subscriptions_router
app.include_router(twin_subscriptions_router)

from app.api.briefings import router as briefings_router
app.include_router(briefings_router)

from app.api.academic_cards import router as academic_cards_router
app.include_router(academic_cards_router)

from app.api.card_pushes import router as card_pushes_router
app.include_router(card_pushes_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.SERVICE_PORT)
