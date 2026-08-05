"""审计客户端测试 — before_value/after_value 透传（mock HTTP，不连真实服务）"""
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
async def test_write_audit_log_forwards_before_after_values():
    """after_value/before_value 必须进入 JSON payload（画像更新留痕依赖）"""
    fake = _FakeClient()
    with patch("app.services.audit_client.httpx.AsyncClient", return_value=fake), \
         patch("app.services.audit_client.internal_headers", return_value={"X-Internal-Key": "test-key"}):
        log_id = await write_audit_log(
            action="hcp_profile_update_from_visit",
            before_value={"tags": ["KOL"]},
            after_value={"source": "ai_visit", "visit_id": 1, "updated": ["tags"]},
        )
    assert log_id == 42
    payload = fake.post.await_args.kwargs["json"]
    assert payload["before_value"] == {"tags": ["KOL"]}
    assert payload["after_value"]["source"] == "ai_visit"


@pytest.mark.asyncio
async def test_write_audit_log_omits_none_values():
    """未传 before_value/after_value 时 payload 不携带这两个键"""
    fake = _FakeClient()
    with patch("app.services.audit_client.httpx.AsyncClient", return_value=fake), \
         patch("app.services.audit_client.internal_headers", return_value={"X-Internal-Key": "test-key"}):
        await write_audit_log(action="visit_start")
    payload = fake.post.await_args.kwargs["json"]
    assert "before_value" not in payload
    assert "after_value" not in payload
    assert payload["action"] == "visit_start"
