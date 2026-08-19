"""认证服务 - FastAPI 入口"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
from contextlib import asynccontextmanager

from app.config import settings
from shared.common.exception_handler import register_exception_handlers
from shared.common.request_id_middleware import RequestIDMiddleware

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 这个服务负责签发 token —— 密钥没配好就不能启动，
# 否则会用 shared 里的兜底密钥 dev-secret-change-me 签出可被任意伪造的 token。
_WEAK_SECRETS = {"", "dev-secret-change-me", "change_me_to_a_random_secret_string"}
if settings.JWT_SECRET in _WEAK_SECRETS:
    raise RuntimeError(
        "JWT_SECRET 未配置或仍是默认值，auth-service 拒绝启动。"
        "请在 .env 中设置一个足够随机的 JWT_SECRET（例：openssl rand -hex 32）。"
    )

if settings.DEV_MODE:
    logger.warning("AUTH_DEV_MODE=true：send-code 会在响应体里回传验证码，生产环境必须关闭！")

async def _filing_expiry_loop() -> None:
    """备案到期扫描：启动即跑一次，此后每 QUALIFICATION_CHECK_INTERVAL_HOURS 小时执行（参照 audit-service 清理任务模式）"""
    from app.core.filing_expiry import run_filing_expiry_scan

    while True:
        try:
            await run_filing_expiry_scan()
        except Exception as exc:
            logger.error("备案到期扫描失败: %s", exc)
        await asyncio.sleep(settings.QUALIFICATION_CHECK_INTERVAL_HOURS * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_filing_expiry_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="MedAgent - 认证服务",
    description="手机号验证码登录 / 用户名密码登录 / 当前用户信息",
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
# 审计客户端/日志 get_request_id() 取用；无头时生成（服务直连场景兜底）
app.add_middleware(RequestIDMiddleware)

register_exception_handlers(app)

from app.api.auth import router as auth_router
app.include_router(auth_router)

from app.api.users import router as users_router
app.include_router(users_router)

from app.api.qualifications import router as qualifications_router
app.include_router(qualifications_router)

from app.api.doctors import router as doctors_router
app.include_router(doctors_router)

from app.api.training_materials import router as training_materials_router
app.include_router(training_materials_router)

from app.api.exams import router as exams_router
app.include_router(exams_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.SERVICE_PORT)
