"""
FastAPI 全局异常处理器

将自定义 AppError / HTTPException / RequestValidationError 统一转换为
{code, message, data} 错误响应格式。
所有微服务只需注册一次即可（网关不注册 —— 有自己的统一渲染）。
"""

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from shared.common.response import AppError


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """处理 AppError 及其子类（ParamError / AuthError / BusinessError 等）"""
    return JSONResponse(
        status_code=_code_to_http_status(exc.code),
        content={
            "code": exc.code,
            "message": exc.message,
            "data": exc.data,
        }
    )


# HTTP 状态码 → 业务错误码映射（S1，2026-08-13）。
# 只用于"未携带 code 的裸 HTTPException"：按 HTTP 语义映射，message 取 detail 字符串，
# 让 404/405/429 等不再以 {"detail": "..."} 的 FastAPI 默认形状返给前端。
_STATUS_CODE_MAP = {
    400: 1000,  # 参数错误
    401: 2000,  # 认证错误
    403: 3000,  # 权限错误
    404: 4000,  # 资源不存在（业务错误）
    405: 1000,  # 方法不允许 → 参数/调用错误
    429: 5003,  # 限流（与网关 rate_limiter 的 5003 一致）
    500: 5000,  # 系统错误
}


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException → 统一 {code, message, data}（S1，2026-08-13）。

    - detail 是 dict 且含 "code" 键：按原语义渲染 —— 保住 shared/common/auth.py
      verify_token/get_current_user 的 2001/2002/2003 与 internal_auth 的 3001；
    - 其余（detail 为 str / None / 其他类型）：按 status 映射 code，
      message 取 detail（str；None 或非 str → "请求失败"），data 为 None。
    """
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        content = {
            "code": detail["code"],
            "message": detail.get("message", "请求失败"),
            "data": detail.get("data"),
        }
    else:
        content = {
            "code": _STATUS_CODE_MAP.get(exc.status_code, 5000),
            "message": detail if isinstance(detail, str) else "请求失败",
            "data": None,
        }
    # headers 透传（HTTPException 可携带如 WWW-Authenticate 等头）
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """RequestValidationError（FastAPI 参数校验失败）→ code 1000（S1，2026-08-13）。

    message 附带首条错误的字段路径（如 body.phone），便于前端/联调定位。
    """
    loc = ""
    try:
        errors = exc.errors()
        if errors:
            loc = ".".join(str(p) for p in errors[0].get("loc", ()))
    except Exception:  # 防御：解析失败不拖垮错误渲染
        pass
    message = f"参数校验失败：{loc}" if loc else "参数校验失败"
    return JSONResponse(
        status_code=422,
        content={"code": 1000, "message": message, "data": None},
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底处理未预期的异常"""
    import logging
    logger = logging.getLogger(__name__)
    logger.exception(f"未处理的异常: {request.method} {request.url}")

    return JSONResponse(
        status_code=500,
        content={
            "code": 5000,
            "message": "服务器内部错误",
            "data": None,
        }
    )


def register_exception_handlers(app):
    """为一 FastAPI 应用注册全局异常处理器"""
    from shared.common.response import AppError
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)


def _code_to_http_status(code: int) -> int:
    """根据业务错误码映射 HTTP 状态码"""
    if code == 0:
        return 200
    if 1000 <= code < 2000:
        return 400       # 参数错误 → 400
    if 2000 <= code < 3000:
        return 401       # 认证错误 → 401
    if 3000 <= code < 4000:
        return 403       # 权限错误 → 403
    if code == 4000:
        return 404       # 资源不存在 → 404（2026-08-26 统一：4000 专指资源不存在）
    if 4000 <= code < 5000:
        return 422       # 其余业务错误 → 422
    if 5000 <= code < 6000:
        return 500       # 系统错误 → 500
    if 6000 <= code < 7000:
        return 502       # 第三方错误 → 502
    return 500
