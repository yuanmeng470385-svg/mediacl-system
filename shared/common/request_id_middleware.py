"""
X-Request-ID 链路追踪中间件（需求 7.1：每个请求必须携带 X-Request-ID（UUID））

全链路贯穿方式（网关是全部流量的唯一入口）：
1. 网关注册本中间件（最外层）：请求头无 X-Request-ID 则生成 uuid4 注入 scope，
   有则校验（长度上限防滥用）后沿用；proxy 转发时以 scope 中的校验值为准
   覆盖上游请求头 —— 上游一定收到同一链路 ID，web/mobile/内部调用全贯穿。
2. 各业务服务注册同款中间件：从请求头读取同一 ID 写入 context
   （shared/common/context.py 的 set_request_id），服务内 logger / 审计
   get_request_id() 即得全链路 ID。
3. 服务间内部调用（internal_headers()）从 context 取 ID 带上，
   context 为空（后台任务等）则生成 —— 内部调用同样可追踪。

设计说明：
- 纯透传：只读请求头、写 context/scope，不改响应、不读 body，
  对任何响应类型（JSON / 流式 / 文件下载）无副作用。
- WebSocket 握手路径不受影响：非 http scope 直接透传（不生成、不注入 ID），
  网关 WS 代理、chat_ws / asr_ws 等保持原行为。
- OPTIONS 预检直接放行（CORS 中间件短路处理，不产生业务链路），
  不因本中间件引入任何预检逻辑（H10 教训）。
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from shared.common.context import set_request_id, generate_request_id

logger = logging.getLogger(__name__)

# 上限与 shared/models/audit_log.py 的 request_id 列（String(100)）对齐；
# 调用方塞超长值视为滥用，重新生成。
MAX_REQUEST_ID_LEN = 100


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求建立 X-Request-ID 并写入 context / scope。"""

    async def dispatch(self, request: Request, call_next):
        # WebSocket 握手 / lifespan 等 scope 不进入链路逻辑，原样透传
        if request.scope.get("type") != "http":
            return await call_next(request)
        # OPTIONS 预检由 CORS 短路处理，不产生业务链路，不生成 ID
        if request.method == "OPTIONS":
            return await call_next(request)

        rid = _validated(request.headers.get("x-request-id"))
        if not rid:
            rid = generate_request_id()
        set_request_id(rid)
        # proxy 转发时以 scope 中的校验值为准覆盖上游请求头
        request.scope["x-request-id"] = rid
        return await call_next(request)


def _validated(value: str) -> str:
    """校验调用方传入的 X-Request-ID：非空、长度不超限、不含空白/控制字符。"""
    value = (value or "").strip()
    if not value or len(value) > MAX_REQUEST_ID_LEN:
        return ""
    if any(ch in value for ch in (" ", "\t", "\r", "\n")):
        return ""
    return value
