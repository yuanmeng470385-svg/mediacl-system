"""
FastAPI 全局异常处理器

将自定义 AppError 转换为统一错误响应格式。
所有微服务只需注册一次即可。
"""

from fastapi import Request
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
    if 4000 <= code < 5000:
        return 422       # 业务错误 → 422
    if 5000 <= code < 6000:
        return 500       # 系统错误 → 500
    if 6000 <= code < 7000:
        return 502       # 第三方错误 → 502
    return 500
