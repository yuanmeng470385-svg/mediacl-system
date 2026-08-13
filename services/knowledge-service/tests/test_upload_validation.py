"""M24/M26 修复单测：上传校验 + 未上架文档访问控制

- M24: 扩展名白名单（.doc/.ppt 旧格式拒绝）、50MB 大小上限、approved 字符串 "false" → False
- M26: 非审核角色（rep）列表只返回 ready；详情对 draft/rejected/archived 文档不可见
端点测试通过 TestClient + 依赖覆盖进行，无真实 DB/OSS。
"""
import pytest
from fastapi.testclient import TestClient

from app.api.knowledge import _parse_bool_value, _can_view_all_documents
from shared.common.response import ParamError


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """避免 TestClient 依赖覆盖泄漏到其他测试"""
    from app.main import app
    yield
    app.dependency_overrides.clear()


# ---------- M24: 纯函数（approved 显式布尔解析 / 角色可见性） ----------

def test_parse_bool_value_string_false_is_false():
    assert _parse_bool_value("false") is False
    assert _parse_bool_value("False") is False
    assert _parse_bool_value("0") is False
    assert _parse_bool_value("no") is False
    assert _parse_bool_value("true") is True
    assert _parse_bool_value("True") is True
    assert _parse_bool_value("1") is True
    assert _parse_bool_value("yes") is True
    assert _parse_bool_value(True) is True
    assert _parse_bool_value(False) is False
    assert _parse_bool_value(1) is True
    assert _parse_bool_value(0) is False
    with pytest.raises(ParamError):
        _parse_bool_value("maybe")
    with pytest.raises(ParamError):
        _parse_bool_value(2)


def test_can_view_all_documents():
    assert _can_view_all_documents({"role": "admin"}) is True
    assert _can_view_all_documents({"role": "manager"}) is True
    assert _can_view_all_documents({"role": "medical"}) is True
    assert _can_view_all_documents({"role": "rep"}) is False
    assert _can_view_all_documents({}) is False


# ---------- 端点级 fakes ----------

class _StubDoc:
    def __init__(self, doc_id=1, status="ready"):
        self.id = doc_id
        self.status = status
        self.title = "t"
        self.doc_type = "guideline"

    def to_dict(self):
        return {"id": self.id, "title": self.title, "status": self.status}


class _StubRepo:
    def __init__(self):
        self.list_status = None
        self.doc = _StubDoc()

    def list_documents(self, status=None, doc_type=None, product_id=None, page=1, page_size=20):
        self.list_status = status
        return [self.doc], 1

    def get(self, doc_id):
        return self.doc


class _StubManager:
    def __init__(self, repo=None):
        self.repo = repo or _StubRepo()
        self.upload_kwargs = None
        self.review_kwargs = None

    def create_from_upload(self, **kw):
        self.upload_kwargs = kw
        return _StubDoc(doc_id=99, status="draft")

    def approve_document(self, doc_id, reviewer_id):
        self.review_kwargs = ("approve", doc_id, reviewer_id)
        return _StubDoc(doc_id=doc_id, status="ready")

    def reject_document(self, doc_id, reviewer_id):
        self.review_kwargs = ("reject", doc_id, reviewer_id)
        return _StubDoc(doc_id=doc_id, status="rejected")


class _FakeUser:
    """require_roles 库查（S6 修复）：主键查 User 返回的 active 用户（role 与 token 一致）"""

    def __init__(self, role):
        self.id = 1
        self.status = "active"
        self.role = role


class _UserQuery:
    def __init__(self, role):
        self._role = role

    def filter(self, *a, **kw):
        return self

    def first(self):
        return _FakeUser(self._role)


class _EmptyQuery:
    """非 User 表查询：空结果（这些测试经 _StubManager 走 fake repo，不触库）"""

    def filter(self, *a, **kw):
        return self

    def order_by(self, *a, **kw):
        return self

    def offset(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def first(self):
        return None

    def all(self):
        return []

    def count(self):
        return 0


class _FakeDb:
    def __init__(self, role="admin"):
        self.role = role

    def query(self, model):
        if getattr(model, "__name__", "") == "User":
            return _UserQuery(self.role)
        return _EmptyQuery()


def _make_client(monkeypatch, role="admin", manager=None):
    from app.main import app
    from shared.common.auth import get_current_user
    from shared.common.db_session import get_db
    import app.api.knowledge as k

    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "username": "u", "role": role}
    app.dependency_overrides[get_db] = lambda: _FakeDb(role)
    k._manager = lambda db: manager or _StubManager()

    async def _noop_audit(*args, **kwargs):
        return None

    k.write_audit_log = _noop_audit
    return TestClient(app)


# ---------- M24: 上传校验 ----------

def test_upload_rejects_legacy_doc(monkeypatch):
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("方案.doc", b"x" * 100, "application/msword")},
        data={"title": "指南", "doc_type": "guideline"},
    )
    assert resp.status_code == 400
    assert "旧版格式" in resp.json()["message"]
    assert "docx" in resp.json()["message"]  # 提示转换
    assert manager.upload_kwargs is None     # 未进入入库逻辑


def test_upload_rejects_legacy_ppt(monkeypatch):
    client = _make_client(monkeypatch, role="admin")
    resp = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("材料.ppt", b"x" * 100, "application/vnd.ms-powerpoint")},
        data={"title": "t", "doc_type": "guideline"},
    )
    assert resp.status_code == 400
    assert "旧版格式" in resp.json()["message"]


def test_upload_rejects_unknown_ext(monkeypatch):
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
        data={"title": "t", "doc_type": "guideline"},
    )
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["message"]
    assert manager.upload_kwargs is None


def test_upload_rejects_oversize(monkeypatch):
    import app.api.knowledge as k
    monkeypatch.setattr(k, "MAX_UPLOAD_SIZE", 2048)     # 测试用小上限
    monkeypatch.setattr(k, "_UPLOAD_READ_CHUNK", 1024)
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("big.txt", b"a" * 4096, "text/plain")},
        data={"title": "t", "doc_type": "guideline"},
    )
    assert resp.status_code == 400
    assert "超过上限" in resp.json()["message"]
    assert manager.upload_kwargs is None


def test_upload_txt_ok(monkeypatch):
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("指南.txt", "剂量 5mg".encode("utf-8"), "text/plain")},
        data={"title": "指南", "doc_type": "guideline"},
    )
    assert resp.status_code == 200
    assert manager.upload_kwargs is not None
    assert manager.upload_kwargs["doc_type"] == "guideline"


# ---------- C3: 上传列长校验（title 500 / source 200 / version 20） ----------

def test_upload_title_too_long_400(monkeypatch):
    """C3：title 超过 500 字符 → 400（否则 DB varchar(500) DataError 500）"""
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("a.txt", b"x", "text/plain")},
        data={"title": "长" * 501, "doc_type": "guideline"},
    )
    assert resp.status_code == 400
    assert "title" in resp.json()["message"]
    assert manager.upload_kwargs is None


def test_upload_source_too_long_400(monkeypatch):
    """C3：source 超过 200 字符 → 400"""
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("a.txt", b"x", "text/plain")},
        data={"title": "t", "doc_type": "guideline", "source": "s" * 201},
    )
    assert resp.status_code == 400
    assert "source" in resp.json()["message"]
    assert manager.upload_kwargs is None


def test_upload_version_too_long_400(monkeypatch):
    """C3：version 超过 20 字符 → 400"""
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("a.txt", b"x", "text/plain")},
        data={"title": "t", "doc_type": "guideline", "version": "v" * 21},
    )
    assert resp.status_code == 400
    assert "version" in resp.json()["message"]
    assert manager.upload_kwargs is None


def test_upload_rep_forbidden(monkeypatch):
    """上传仍限审核角色（admin/manager/medical）"""
    client = _make_client(monkeypatch, role="rep")
    resp = client.post(
        "/api/v1/knowledge/upload",
        files={"file": ("a.txt", b"x", "text/plain")},
        data={"title": "t", "doc_type": "guideline"},
    )
    assert resp.status_code == 403


# ---------- M24: review 的 approved 显式布尔解析 ----------

def test_review_approved_false_string_rejects(monkeypatch):
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post("/api/v1/knowledge/documents/3/review", json={"approved": "false"})
    assert resp.status_code == 200
    assert manager.review_kwargs[0] == "reject"  # 字符串 "false" 必须驳回而非批准


def test_review_approved_true_string_approves(monkeypatch):
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post("/api/v1/knowledge/documents/3/review", json={"approved": "true"})
    assert resp.status_code == 200
    assert manager.review_kwargs[0] == "approve"


def test_review_approved_invalid_raises_param_error(monkeypatch):
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post("/api/v1/knowledge/documents/3/review", json={"approved": "maybe"})
    assert resp.status_code == 400
    assert "布尔值" in resp.json()["message"]
    assert manager.review_kwargs is None


# ---------- C2: review 缺 approved/action 键 → 400（不再默认驳回） ----------

def test_review_missing_keys_400(monkeypatch):
    """C2：approved/action 键都缺 → 400，不再默认按驳回执行高风险动作
    （驳回会清理检索索引、拒绝上架）"""
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post("/api/v1/knowledge/documents/3/review", json={})
    assert resp.status_code == 400
    assert "approved" in resp.json()["message"]
    assert manager.review_kwargs is None


def test_review_action_approve_compat(monkeypatch):
    """C2：旧前端兼容契约 {"action": "approve"} 仍可用"""
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post("/api/v1/knowledge/documents/3/review", json={"action": "approve"})
    assert resp.status_code == 200
    assert manager.review_kwargs[0] == "approve"


def test_review_action_invalid_400(monkeypatch):
    """C2：action 拼写错误（"apporve"）→ 400，不再静默落入驳回分支"""
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.post("/api/v1/knowledge/documents/3/review", json={"action": "apporve"})
    assert resp.status_code == 400
    assert manager.review_kwargs is None


# ---------- M26: 未上架文档访问控制 ----------

def test_list_as_rep_forces_ready(monkeypatch):
    manager = _StubManager()
    client = _make_client(monkeypatch, role="rep", manager=manager)
    resp = client.get("/api/v1/knowledge/documents", params={"status": "draft"})
    assert resp.status_code == 200
    assert manager.repo.list_status == "ready"  # rep 的 status 过滤被强制为 ready


def test_list_as_admin_keeps_requested_status(monkeypatch):
    manager = _StubManager()
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.get("/api/v1/knowledge/documents", params={"status": "draft"})
    assert resp.status_code == 200
    assert manager.repo.list_status == "draft"


def test_get_draft_as_rep_forbidden(monkeypatch):
    manager = _StubManager()
    manager.repo.doc = _StubDoc(doc_id=3, status="draft")
    client = _make_client(monkeypatch, role="rep", manager=manager)
    resp = client.get("/api/v1/knowledge/documents/3")
    assert resp.status_code == 422
    assert "无权访问" in resp.json()["message"]


def test_get_rejected_as_rep_forbidden(monkeypatch):
    manager = _StubManager()
    manager.repo.doc = _StubDoc(doc_id=3, status="rejected")
    client = _make_client(monkeypatch, role="rep", manager=manager)
    resp = client.get("/api/v1/knowledge/documents/3")
    assert resp.status_code == 422


def test_get_draft_as_admin_ok(monkeypatch):
    manager = _StubManager()
    manager.repo.doc = _StubDoc(doc_id=3, status="draft")
    client = _make_client(monkeypatch, role="admin", manager=manager)
    resp = client.get("/api/v1/knowledge/documents/3")
    assert resp.status_code == 200


def test_get_ready_as_rep_ok(monkeypatch):
    manager = _StubManager()
    manager.repo.doc = _StubDoc(doc_id=3, status="ready")
    client = _make_client(monkeypatch, role="rep", manager=manager)
    resp = client.get("/api/v1/knowledge/documents/3")
    assert resp.status_code == 200
