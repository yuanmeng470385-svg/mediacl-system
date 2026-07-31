"""
请求上下文工具

- X-Request-ID 生成与传递
- 请求耗时统计
"""

import uuid
import time
from contextvars import ContextVar
from typing import Optional

# 上下文变量（每个请求独立）
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
request_start_time_var: ContextVar[float] = ContextVar("request_start_time", default=0.0)


def generate_request_id() -> str:
    """生成 UUID 格式的请求 ID"""
    return str(uuid.uuid4())


def set_request_id(request_id: Optional[str] = None) -> str:
    """设置当前请求的 Request ID"""
    rid = request_id or generate_request_id()
    request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    """获取当前请求的 Request ID"""
    return request_id_var.get()


def mark_request_start():
    """标记请求开始时间"""
    request_start_time_var.set(time.time())


def get_elapsed_ms() -> float:
    """获取当前请求已耗时（毫秒）"""
    start = request_start_time_var.get()
    if start == 0.0:
        return 0.0
    return (time.time() - start) * 1000
