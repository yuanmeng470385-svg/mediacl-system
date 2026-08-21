"""隐私请求（三期 L，需求 3.8(4)(5)/5.7）：提交/本人查询/管理端处理

Task 1 仅建骨架挂路由；端点在 Task 3/4 实现。
write_audit_log 先占位 import——测试 fixture 对它做 monkeypatch.setattr，
属性必须存在（Task 3 替换全文后真正使用）。
"""
import logging

from fastapi import APIRouter

from app.services.audit_client import write_audit_log  # noqa: F401（fixture 打桩锚点）

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/privacy-requests", tags=["privacy-requests"])
