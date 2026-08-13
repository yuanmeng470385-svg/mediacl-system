"""专员列表分页 / stats 计数 / create/update 白名单（API 级，FakeDb 替身）

契约回归 2026-08-06：
- GET /specialists 返回 paginate() 形状 {items,total,page,page_size,pagination}，
  缺省不过滤 status（web 需看 draft/disabled）
- stats.total_conversations 只数 role='user' 行（每轮落 2 行，避免双倍）
- satisfaction_rate 语义 0-100 百分数
- create/update 只接受白名单字段，status 只能是 draft/active/disabled
"""
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.api.conversations import get_current_user
from shared.common.db_session import get_db
from app.models.specialist import Specialist


class FakeSpecialist:
    """与 Specialist.to_dict() 同构的行替身"""

    def __init__(self, id, name, status, product_id=1):
        self.id = id
        self.name = name
        self.product_id = product_id
        self.persona = None
        self.compliance_level = "internal"
        self.bailian_app_id = f"mm_{id}"
        self.status = status
        self.created_at = datetime(2026, 8, 1)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "product_id": self.product_id,
            "persona": self.persona, "compliance_level": self.compliance_level,
            "bailian_app_id": self.bailian_app_id, "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class ChainStub:
    """query().filter().count() / ...offset().limit().all() 链式替身（记录 filter 调用）"""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.filters = []
        self.offset_args = None
        self.limit_args = None

    def filter(self, *a, **k):
        self.filters.append((a, k))
        return self

    def order_by(self, *a, **k):
        return self

    def count(self):
        return len(self.rows)

    def offset(self, n):
        self.offset_args = n
        return self

    def limit(self, n):
        self.limit_args = n
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class ScalarStub(ChainStub):
    """func.count(...) 查询：scalar() 依次弹出预置值"""

    def __init__(self, values=None):
        super().__init__([])
        self.values = list(values or [])

    def scalar(self):
        return self.values.pop(0) if self.values else 0


class UserStub:
    """users 表主键查询：require_roles 库查（S6 修复）返回 active 用户（role 取 db.user_role）"""

    def __init__(self, db):
        self._db = db

    def filter(self, *a, **k):
        return self

    def first(self):
        user = FakeUser()
        user.role = self._db.user_role
        return user


class FakeUser:
    def __init__(self):
        self.id = 1
        self.status = "active"
        self.role = "admin"


class FakeDb:
    """按模型分发 stubs，stub 在请求后仍可被测试检查（filter 调用记录）"""

    def __init__(self, specialists=None):
        self.specialist_stub = ChainStub(specialists or [])
        self.conv = ScalarStub()
        self.feedback = ScalarStub()
        # D2（2026-08-13）：create/update 预检产品存在性 —— 默认有一行产品
        # （first() 返回 truthy 即"存在"）
        self.product_stub = ChainStub([object()])
        self.added = []
        self.user_role = "admin"  # _client 按 role 参数覆写

    def query(self, model):
        # func.count(Conversation.id) 不是模型类——从函数参数的列上取表名
        table = getattr(model, "__table__", None)
        if table is None:
            clause = next(iter(getattr(model, "clauses", ())), None)
            table = getattr(clause, "table", None)
        name = getattr(table, "name", None) or getattr(model, "__name__", None)
        if name == "digital_specialists":
            return self.specialist_stub
        if name == "products":
            return self.product_stub
        if name == "conversations":
            return self.conv
        if name == "conversation_feedback":
            return self.feedback
        if name == "users":
            return UserStub(self)
        raise AssertionError(f"unexpected table: {name}")

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        obj.id = 1


def _client(db: FakeDb, role: str = "admin"):
    db.user_role = role  # require_roles 库查（S6 修复）：库内角色与 token 角色一致
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "role": role}
    return TestClient(app)


def _has_filter(stub, left_key, right_value):
    for args, _ in stub.filters:
        for e in args:
            if getattr(getattr(e, "left", None), "key", None) == left_key and \
                    getattr(getattr(e, "right", None), "value", None) == right_value:
                return True
    return False


# ==================== 列表：分页形状 + status 过滤 ====================

def test_list_returns_paginate_shape_and_all_statuses():
    db = FakeDb(specialists=[
        FakeSpecialist(1, "A", "active"),
        FakeSpecialist(2, "B", "draft"),
        FakeSpecialist(3, "C", "disabled"),
    ])
    resp = _client(db).get("/api/v1/specialists")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert set(data) == {"items", "total", "page", "page_size", "pagination"}
    assert data["total"] == 3
    assert data["page"] == 1 and data["page_size"] == 20
    assert [i["name"] for i in data["items"]] == ["A", "B", "C"]  # draft/disabled 可见
    assert data["pagination"]["total_pages"] == 1
    # 不传 status → 不做任何过滤（web 要看全部状态）
    assert db.specialist_stub.filters == []


def test_list_filters_by_status():
    db = FakeDb(specialists=[
        FakeSpecialist(1, "A", "active"),
        FakeSpecialist(2, "B", "draft"),
    ])
    resp = _client(db).get("/api/v1/specialists", params={"status": "active"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["total"] == 2
    assert _has_filter(db.specialist_stub, "status", "active")
    # 非法 status 值照常下发（服务端不校验枚举，前端自己约束）
    resp2 = _client(db).get("/api/v1/specialists", params={"status": "intern"})
    assert resp2.status_code == 200
    assert _has_filter(db.specialist_stub, "status", "intern")


def test_list_pagination_params_passed_through():
    db = FakeDb(specialists=[FakeSpecialist(i, f"S{i}", "active") for i in range(1, 6)])
    resp = _client(db).get("/api/v1/specialists", params={"page": 2, "page_size": 2})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["page"] == 2 and data["page_size"] == 2
    assert db.specialist_stub.offset_args == 2
    assert db.specialist_stub.limit_args == 2
    assert data["pagination"]["has_prev"] is True
    assert data["pagination"]["has_next"] is True
    assert data["pagination"]["total_pages"] == 3


# ==================== stats：role='user' 计数 + 0-100 满意度 ====================

def test_stats_counts_only_user_rows_and_returns_0_100():
    db = FakeDb(specialists=[FakeSpecialist(1, "A", "active")])
    db.conv.values = [7]        # 只有 7 行 role='user'
    db.feedback.values = [3, 1]  # 3 赞 1 踩 → 75%
    resp = _client(db).get("/api/v1/specialists/1/stats")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total_conversations"] == 7
    assert data["total_feedback"] == 4
    assert data["satisfaction_rate"] == 75  # 0-100，非 0.75
    assert _has_filter(db.conv, "role", "user")


def test_stats_satisfaction_none_when_no_feedback():
    db = FakeDb(specialists=[FakeSpecialist(1, "A", "active")])
    db.conv.values = [3]
    db.feedback.values = [0, 0]
    resp = _client(db).get("/api/v1/specialists/1/stats")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_conversations"] == 3
    assert data["satisfaction_rate"] is None


def test_stats_404_when_specialist_missing():
    resp = _client(FakeDb()).get("/api/v1/specialists/999/stats")
    assert resp.status_code == 404


# ==================== feedback：仅 admin/manager（G4 2026-08-13） ====================

def test_feedback_requires_admin_or_manager():
    """G4 回归：反馈明细含全部用户问答快照（web 后台专用），rep 访问 → 403"""
    db = FakeDb(specialists=[FakeSpecialist(1, "A", "active")])
    resp = _client(db, role="rep").get("/api/v1/specialists/1/feedback")
    assert resp.status_code == 403


def test_feedback_admin_returns_200():
    """G4 回归：admin 访问反馈明细正常（空明细时 200 + 空 items）"""
    db = FakeDb(specialists=[FakeSpecialist(1, "A", "active")])
    resp = _client(db, role="admin").get("/api/v1/specialists/1/feedback")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


# ==================== create/update：白名单行为 ====================

def test_create_accepts_whitelist_fields():
    db = FakeDb()
    resp = _client(db).post("/api/v1/specialists", json={
        "name": "肿瘤专员", "product_id": 3, "bailian_app_id": "mm_x",
        "compliance_level": "high", "status": "active",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["id"] == 1
    assert len(db.added) == 1
    created = db.added[0]
    assert created.name == "肿瘤专员"
    assert created.product_id == 3
    assert created.status == "active"
    assert created.compliance_level == "high"


def test_create_rejects_non_whitelist_fields():
    db = FakeDb()
    resp = _client(db).post("/api/v1/specialists", json={
        "name": "A", "product_id": 1, "style": "professional", "description": "x",
    })
    assert resp.status_code == 400
    assert "style" in resp.json()["message"]
    assert db.added == []


def test_create_requires_name_and_product_id():
    db = FakeDb()
    assert _client(db).post("/api/v1/specialists", json={"product_id": 1}).status_code == 400
    assert _client(db).post("/api/v1/specialists", json={"name": "A"}).status_code == 400


def test_update_only_applies_whitelist_and_valid_status():
    db = FakeDb(specialists=[FakeSpecialist(1, "原名", "active")])
    resp = _client(db).put("/api/v1/specialists/1", json={"name": "新名", "status": "disabled"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "disabled"
    assert resp.json()["data"]["name"] == "新名"
    # 白名单外的字段 → 400（契约：web 表单不再发 style/description）
    resp2 = _client(db).put("/api/v1/specialists/1", json={"status": "disabled", "hack": 1})
    assert resp2.status_code == 400
    # 后端不存在的 status（intern）→ 400
    resp3 = _client(db).put("/api/v1/specialists/1", json={"status": "intern"})
    assert resp3.status_code == 400


def test_update_404_when_specialist_missing():
    resp = _client(FakeDb()).put("/api/v1/specialists/999", json={"name": "A"})
    assert resp.status_code == 404
