"""审计服务 - FastAPI 入口"""
import sys
import os
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

app = FastAPI(
    title="MedAgent - 审计服务",
    description="不可篡改审计日志、高级搜索、监管报告导出",
    version="1.0.0"
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
