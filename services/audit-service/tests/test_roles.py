"""审计端点角色限制测试（S6 RBAC 补漏：查询/详情/stats/导出仅 admin/manager/compliance）"""
import os
import sys
import logging
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
# 测试不连真实数据库：隔离前先改 DATABASE_URL，且下面统一 override get_db
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# /log 内部接口的 X-Internal-Key 校验（测试用固定值；get_internal_api_key
# 首次调用时读环境，弱值守卫在 app 启动时未触发）
os.environ["INTERNAL_API_KEY"] = "test-internal-key-20260813"

import pytest
from fastapi.testclient import TestClient

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)

from app.main import app
from shared.common.auth import create_token
from shared.common.db_session import get_db


class _FakeUser:
    """require_roles 库查（S6 修复）：主键查 User 返回的用户（status 可配）"""

    def __init__(self, role, status="active"):
        self.id = 1
        self.username = "tester"
        self.status = status
        self.role = role


class _UserQueryStub:
    """users 表查询 stub：first() 返回 role/status 取 mock_db.user_role/user_status 的用户"""

    def __init__(self, mock_db):
        self._db = mock_db

    def filter(self, *a, **k):
        return self

    def first(self):
        return _FakeUser(self._db.user_role, self._db.user_status)


def _make_mock_db():
    """模拟数据库 session：日志查询返回空结果；User 主键查询返回 active 用户
    （role 取 mock_db.user_role，默认 admin —— 各测试按 token 角色显式设置；
    status 取 mock_db.user_status，默认 active，停用用例显式改 disabled）"""
    mock_db = MagicMock()
    mock_db.user_role = "admin"
    mock_db.user_status = "active"
    q = mock_db.query.return_value
    q.count.return_value = 0
    q.scalar.return_value = 0
    q.all.return_value = []
    # 详情页：query().filter().first() → 日志不存在（ParamError）
    q.filter.return_value.first.return_value = None
    # 列表页：query().order_by().offset().limit().all()
    q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
    # 导出：query().order_by().limit().all()；带筛选时 count/all 都落在 filter 链上
    q.order_by.return_value.limit.return_value.all.return_value = []
    fq = q.filter.return_value
    fq.filter.return_value = fq   # 多重过滤自环：任意层级行为一致
    fq.count.return_value = 0
    fq.order_by.return_value.limit.return_value.all.return_value = []

    def _query(*models):
        # require_roles 每次受限请求主键查一次库（S6 修复）：User 走用户 stub，其余走日志 stub
        # （stats 等端点可能 query(Log, func.count(...)) 多参查询，只按首个模型路由）
        if models and getattr(models[0], "__name__", "") == "User":
            return _UserQueryStub(mock_db)
        return q

    mock_db.query.side_effect = _query
    return mock_db


@pytest.fixture
def client():
    mock_db = _make_mock_db()

    def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as c:
        yield c, mock_db
    app.dependency_overrides.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _token(role: str) -> str:
    return create_token(user_id=1, username=f"{role}_user", role=role)


class TestAuditLogsRoleRestriction:
    """查询/详情/stats/导出端点角色限制：admin/manager/compliance 可看，rep 403"""

    def test_disabled_user_old_token_rejected(self, client):
        """H2：账号停用后，旧 token（有效期内）调受限端点 → 401（实时查库）。
        S1（2026-08-13）起 shared 异常处理器把含 code 的 HTTPException detail
        原样平铺成 {code, message, data}，按顶层 code 断言"""
        c, mock_db = client
        mock_db.user_status = "disabled"
        resp = c.get("/api/v1/audit/logs", headers=_auth(_token("admin")))
        assert resp.status_code == 401
        assert resp.json()["code"] == 2003

    def test_rep_forbidden_on_logs(self, client):
        """rep 角色调 GET /logs → 403（code 3000）"""
        c, mock_db = client
        mock_db.user_role = "rep"
        resp = c.get("/api/v1/audit/logs", headers=_auth(_token("rep")))
        assert resp.status_code == 403
        assert resp.json()["code"] == 3000

    def test_rep_forbidden_on_log_detail(self, client):
        """rep 角色调 GET /logs/{id} → 403"""
        c, mock_db = client
        mock_db.user_role = "rep"
        resp = c.get("/api/v1/audit/logs/1", headers=_auth(_token("rep")))
        assert resp.status_code == 403
        assert resp.json()["code"] == 3000

    def test_rep_forbidden_on_stats(self, client):
        """rep 角色调 GET /stats → 403"""
        c, mock_db = client
        mock_db.user_role = "rep"
        resp = c.get("/api/v1/audit/stats", headers=_auth(_token("rep")))
        assert resp.status_code == 403
        assert resp.json()["code"] == 3000

    def test_rep_forbidden_on_export(self, client):
        """rep 角色调 POST /logs/export → 403（导出含全量数据，更不能对 rep 开放）"""
        c, mock_db = client
        mock_db.user_role = "rep"
        resp = c.post("/api/v1/audit/export", headers=_auth(_token("rep")), json={})
        assert resp.status_code == 403
        assert resp.json()["code"] == 3000

    def test_admin_allowed_on_logs(self, client):
        """admin 角色查日志 → 200"""
        c, mock_db = client
        mock_db.user_role = "admin"
        resp = c.get("/api/v1/audit/logs", headers=_auth(_token("admin")))
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["items"] == []

    def test_manager_allowed_on_stats(self, client):
        """manager 角色调 GET /stats → 200"""
        c, mock_db = client
        mock_db.user_role = "manager"
        resp = c.get("/api/v1/audit/stats", headers=_auth(_token("manager")))
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_compliance_allowed_on_detail(self, client):
        """compliance 角色看单条日志 → 角色已放行（日志不存在走业务 ParamError 400，而非 403）"""
        c, mock_db = client
        mock_db.user_role = "compliance"
        resp = c.get("/api/v1/audit/logs/999", headers=_auth(_token("compliance")))
        assert resp.status_code == 400
        assert resp.json()["code"] == 1000

    def test_export_writes_audit_log(self, client):
        """导出成功后写一条审计日志（action=audit_report_export，含 user_id/筛选摘要/client_ip）"""
        c, mock_db = client
        with patch("app.api.logs.audit_logger") as mock_logger:
            resp = c.post(
                "/api/v1/audit/export",
                headers=_auth(_token("admin")),
                json={
                    "start_time": "2026-07-01T00:00:00",
                    "end_time": "2026-07-31T23:59:59",
                    "risk_level": "high",
                },
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument"
        )
        mock_logger.log.assert_called_once()
        _, kwargs = mock_logger.log.call_args
        assert kwargs["action"] == "audit_report_export"
        assert kwargs["user_id"] == 1
        assert kwargs["resource_type"] == "audit_report"
        assert kwargs["service_name"] == "audit-service"
        assert kwargs["after_value"]["start_time"] == "2026-07-01T00:00:00"
        assert kwargs["after_value"]["end_time"] == "2026-07-31T23:59:59"
        assert kwargs["after_value"]["risk_level"] == "high"
        assert kwargs["client_ip"]  # TestClient 下为 testserver


class TestLogsParamValidation:
    """A3/A4：参数健壮性——非 dict body 与非法时间格式都给 ParamError 400
    （code 1000），不再落 AttributeError/DB 比较异常"""

    def test_log非dict_body返回参数错误(self, client):
        """A3：内部 /log 收到 JSON 数组等非对象 → 4xx code 1000（FastAPI 预校验
        422 或端点 isinstance 校验 400），不落 `**request` 解包/AttributeError 500"""
        c, mock_db = client
        resp = c.post(
            "/api/v1/audit/log",
            headers={"X-Internal-Key": "test-internal-key-20260813"},
            json=["not", "a", "dict"],
        )
        assert resp.status_code in (400, 422)
        assert resp.json()["code"] == 1000

    def test_search非法start_time返回参数错误(self, client):
        """A4：GET /logs 的 start_time 非法 ISO → 400 code 1000"""
        c, mock_db = client
        resp = c.get(
            "/api/v1/audit/logs",
            headers=_auth(_token("admin")),
            params={"start_time": "not-a-date"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 1000

    def test_search非法end_time返回参数错误(self, client):
        """A4：GET /logs 的 end_time 非法 ISO → 400 code 1000"""
        c, mock_db = client
        resp = c.get(
            "/api/v1/audit/logs",
            headers=_auth(_token("admin")),
            params={"end_time": "2026/07/31 23:59:59"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 1000

    def test_search合法时间格式不报参数错误(self, client):
        """A4 正向：合法 ISO 时间（含带时区）正常查询，不误伤"""
        c, mock_db = client
        # 链式 filter 保持同一 stub，让 count/all 返回预设值（mock 里
        # 每次 .filter() 默认返回新的 MagicMock，会吃掉预设的返回值）
        q = mock_db.query.return_value
        q.filter.return_value = q
        resp = c.get(
            "/api/v1/audit/logs",
            headers=_auth(_token("admin")),
            params={"start_time": "2026-07-01T00:00:00",
                    "end_time": "2026-07-31T23:59:59+08:00"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_export非法start_time返回参数错误(self, client):
        """A4：POST /export 的 start_time 非法 ISO → 400 code 1000，且不生成
        导出文件、不写导出审计"""
        c, mock_db = client
        with patch("app.api.logs.audit_logger") as mock_logger:
            resp = c.post(
                "/api/v1/audit/export",
                headers=_auth(_token("admin")),
                json={"start_time": "garbage"},
            )
        assert resp.status_code == 400
        assert resp.json()["code"] == 1000
        mock_logger.log.assert_not_called()
