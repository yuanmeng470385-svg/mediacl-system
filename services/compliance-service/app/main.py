"""合规审核服务 - FastAPI 入口"""
import sys
import os
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

app = FastAPI(
    title="MedAgent - 合规审核服务",
    description="三层合规审核引擎：关键词 + 正则 + LLM 语义",
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
# 服务内日志/审计 get_request_id() 取用；无头时生成（服务直连场景兜底）
app.add_middleware(RequestIDMiddleware)

# 注册全局异常处理器
register_exception_handlers(app)

# 挂载路由
from app.api.rules import router as rules_router
app.include_router(rules_router)

from app.api import report as report_api
app.include_router(report_api.router)

from app.api import metrics as metrics_api
app.include_router(metrics_api.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.SERVICE_NAME, "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.SERVICE_PORT)
