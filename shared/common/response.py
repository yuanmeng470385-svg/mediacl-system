"""
统一 API 响应格式

成功响应:
    {"code": 0, "message": "success", "data": {...}}

错误响应:
    {"code": 4001, "message": "合规拦截", "data": {"rule_code": "R001"}}
"""

from typing import Any, Optional, Dict
from dataclasses import dataclass, asdict


@dataclass
class APIResponse:
    code: int
    message: str
    data: Optional[Any] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def success(data: Any = None, message: str = "success") -> Dict:
    """构建成功响应"""
    return {
        "code": 0,
        "message": message,
        "data": data
    }


def error(code: int, message: str, data: Any = None) -> Dict:
    """构建错误响应

    错误码区间:
        1000-1999  参数错误
        2000-2999  认证错误
        3000-3999  权限错误
        4000-4999  业务错误（含合规拦截）
        5000-5999  系统错误
        6000-6999  第三方服务错误
    """
    return {
        "code": code,
        "message": message,
        "data": data
    }


class AppError(Exception):
    """应用异常基类"""
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class ParamError(AppError):
    """参数错误 (1000-1999)"""
    def __init__(self, message: str, data: Any = None):
        super().__init__(1000, message, data)


class AuthError(AppError):
    """认证错误 (2000-2999)"""
    def __init__(self, message: str = "未登录或 token 已过期", data: Any = None):
        super().__init__(2000, message, data)


class PermissionError(AppError):
    """权限错误 (3000-3999)"""
    def __init__(self, message: str = "无操作权限", data: Any = None):
        super().__init__(3000, message, data)


class BusinessError(AppError):
    """业务错误 (4000-4999)"""
    def __init__(self, message: str, code: int = 4000, data: Any = None):
        super().__init__(code, message, data)
