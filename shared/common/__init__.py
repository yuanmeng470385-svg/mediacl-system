"""共享层通用工具"""
from shared.common.response import success, error, APIResponse, AppError, ParamError, AuthError, BusinessError
from shared.common.auth import create_token, verify_token, get_current_user
from shared.common.pagination import paginate, PaginationParams
from shared.common.db_session import get_db, init_db, SessionLocal
from shared.common.exception_handler import register_exception_handlers
from shared.common.context import get_request_id, set_request_id, mark_request_start, get_elapsed_ms, generate_request_id

__all__ = [
    # 响应
    "success", "error", "APIResponse",
    "AppError", "ParamError", "AuthError", "BusinessError",
    # 认证
    "create_token", "verify_token", "get_current_user",
    # 分页
    "paginate", "PaginationParams",
    # 数据库
    "get_db", "init_db", "SessionLocal",
    # 异常处理
    "register_exception_handlers",
    # 上下文
    "get_request_id", "set_request_id", "mark_request_start",
    "get_elapsed_ms", "generate_request_id",
]
