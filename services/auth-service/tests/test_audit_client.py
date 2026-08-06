"""write_audit_log 单元测试 — mock httpx，验证 before_value/after_value 随请求体透传

回归背景：users.py 的 PUT 更新以 before_value=... 调 write_audit_log，
旧签名没有该参数也没有 **kwargs → 每次更新 db.commit() 后抛 TypeError 返回 500。
此处断言 before_value 必须进入 payload（旧签名下该测试会直接 TypeError 失败）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, patch

from app.services.audit_client import write_audit_log


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"data": {"id": 42}}


class _FakeClient:
    def __init__(self):
        self.post = AsyncMock(return_value=_FakeResp())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_write_audit_log_before_value随请求体透传():
    """user_update 的变更前后快照必须进 payload"""
    fake = _FakeClient()
    with patch("app.services.audit_client.httpx.AsyncClient", return_value=fake), \
         patch("app.services.audit_client.internal_headers", return_value={"X-Internal-Key": "test-key"}):
        log_id = await write_audit_log(
            action="user_update",
            user_id=1,
            resource_type="user",
            resource_id="3",
            before_value={"role": "rep", "status": "active"},
            after_value={"role": "manager"},
        )
    assert log_id == 42
    payload = fake.post.await_args.kwargs["json"]
    assert payload["service_name"] == "auth-service"
    assert payload["action"] == "user_update"
    assert payload["before_value"] == {"role": "rep", "status": "active"}
    assert payload["after_value"] == {"role": "manager"}


@pytest.mark.asyncio
async def test_write_audit_log未传before_value时payload不携带该键():
    """登录/发码等无快照场景不塞 null 键"""
    fake = _FakeClient()
    with patch("app.services.audit_client.httpx.AsyncClient", return_value=fake), \
         patch("app.services.audit_client.internal_headers", return_value={"X-Internal-Key": "test-key"}):
        await write_audit_log(action="auth_send_code")
    payload = fake.post.await_args.kwargs["json"]
    assert "before_value" not in payload
    assert "after_value" not in payload
    assert payload["action"] == "auth_send_code"


@pytest.mark.asyncio
async def test_write_audit_log审计不可用时返回None不抛错():
    """审计服务挂掉时降级：记日志返回 None，不影响业务"""
    fake = _FakeClient()
    fake.post = AsyncMock(side_effect=RuntimeError("audit service down"))
    with patch("app.services.audit_client.httpx.AsyncClient", return_value=fake), \
         patch("app.services.audit_client.internal_headers", return_value={"X-Internal-Key": "test-key"}):
        log_id = await write_audit_log(
            action="user_update",
            user_id=1,
            before_value={"role": "rep"},
            after_value={"role": "manager"},
        )
    assert log_id is None
