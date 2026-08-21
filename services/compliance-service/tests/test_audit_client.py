"""审计写失败可观测回归（2026-08-21 审计遗留：失败仅 logger.error + return None，
无计数指标 —— 审计链路整体失效时监控上完全看不出）"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services import audit_client  # noqa: E402


class _BoomClient:
    """模拟 httpx.AsyncClient 构造/进入即失败（网关不可达）"""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        raise ConnectionError("网关不可达")

    async def __aexit__(self, *a):
        return False


def test_audit_write_failure_counted_and_returns_none(monkeypatch):
    """写失败：业务不受影响（返回 None）+ 失败计数指标 +1（修复前无指标）"""
    from app.api.metrics import COMPLIANCE_AUDIT_WRITE_FAILURES

    monkeypatch.setattr(audit_client.httpx, "AsyncClient", _BoomClient)
    before = COMPLIANCE_AUDIT_WRITE_FAILURES._value.get()
    result = asyncio.run(audit_client.write_audit_log(action="rule_create", user_id=1))
    assert result is None
    assert COMPLIANCE_AUDIT_WRITE_FAILURES._value.get() == before + 1
