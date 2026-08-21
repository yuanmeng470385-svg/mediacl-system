"""审计导出 Excel 公式注入回归（审计遗留 M4：specialist 已修，audit 导出未铺开）"""
import io
import logging
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["INTERNAL_API_KEY"] = "test-internal-key-20260813"

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from app.main import app  # noqa: E402
from shared.common.auth import create_token  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402

EVIL_ACTION = '=HYPERLINK("http://evil.example","点此领取")'


def _fake_log(**over):
    base = dict(
        timestamp=datetime(2026, 8, 1, 10, 0, 0),
        service_name="specialist",
        user_id=1,
        action=EVIL_ACTION,
        resource_type="chat",
        resource_id="1",
        ai_involved=True,
        ai_model="qwen-max",
        risk_level="high",
        request_id="+7020",
    )
    base.update(over)
    return SimpleNamespace(**base)


class _UserQueryStub:
    """require_roles 主键查 User（S6）：恒返回 active admin"""

    def filter(self, *a, **k):
        return self

    def first(self):
        return SimpleNamespace(id=1, username="tester", status="active", role="admin")


def _make_db(rows):
    """导出走 query(AuditLog).order_by().limit().all()；User 查询走用户 stub"""
    db = MagicMock()
    log_q = MagicMock()
    log_q.count.return_value = len(rows)
    log_q.filter.return_value.count.return_value = len(rows)
    log_q.order_by.return_value.limit.return_value.all.return_value = rows

    def _query(*models):
        if models and getattr(models[0], "__name__", "") == "User":
            return _UserQueryStub()
        return log_q

    db.query.side_effect = _query
    db._log_q = log_q   # 截断用例改 count 总数用
    return db


def test_export_sanitizes_formula_cells():
    db = _make_db([_fake_log()])
    app.dependency_overrides[get_db] = lambda: db
    try:
        with patch("app.api.logs.audit_logger"):
            with TestClient(app) as c:
                resp = c.post(
                    "/api/v1/audit/export",
                    headers={"Authorization": "Bearer " + create_token(
                        user_id=1, username="admin_user", role="admin")},
                    json={},
                )
        assert resp.status_code == 200, resp.text
        wb = load_workbook(io.BytesIO(resp.content))
        ws = wb["审计日志"]
        assert ws.cell(row=2, column=4).value == "'" + EVIL_ACTION   # 操作列
        assert ws.cell(row=2, column=10).value == "'+7020"           # 请求ID列
        assert ws.cell(row=2, column=3).value == 1                    # 正常数值不误伤
    finally:
        app.dependency_overrides.clear()


def test_export_truncation_signaled():
    """超过导出上限静默截断 → 表内警示行 + 审计 after_value 带 total/truncated
    （2026-08-21 审计修复：原先导 1 万条封顶，多出来的数据无声消失）"""
    db = _make_db([_fake_log()])
    db._log_q.count.return_value = 10002   # 库里共 10002 条
    app.dependency_overrides[get_db] = lambda: db
    try:
        with patch("app.api.logs.audit_logger") as mock_logger:
            with TestClient(app) as c:
                resp = c.post(
                    "/api/v1/audit/export",
                    headers={"Authorization": "Bearer " + create_token(
                        user_id=1, username="admin_user", role="admin")},
                    json={},
                )
        assert resp.status_code == 200, resp.text
        wb = load_workbook(io.BytesIO(resp.content))
        ws = wb["审计日志"]
        marker = ws.cell(row=3, column=1).value   # 表头 + 1 数据行 + 警示行
        assert marker and "截断" in marker
        assert "10002" in ws.cell(row=3, column=2).value
        after = mock_logger.log.call_args.kwargs["after_value"]
        assert after["truncated"] is True
        assert after["total"] == 10002
        assert after["rows"] == 1
    finally:
        app.dependency_overrides.clear()
