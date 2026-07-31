"""
共享层通用工具
- 统一响应格式
- JWT 认证
- 分页
"""

from .response import success, error, APIResponse
from .auth import create_token, verify_token, get_current_user
from .pagination import paginate, PaginationParams

__all__ = [
    "success", "error", "APIResponse",
    "create_token", "verify_token", "get_current_user",
    "paginate", "PaginationParams",
]
