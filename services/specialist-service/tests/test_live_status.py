"""live-status 接口：注册表 working / 降级推断 / lifecycle offline / summary"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.api.specialists import get_current_user
from shared.common.db_session import get_db
from app.core.activity_registry import registry, PHASE_GENERATING
from app.models.specialist import Specialist


class FakeSpecialist:
    def __init__(self, id, name, status):
        self.id = id
        self.name = name
        self.status = status
        self.created_at = datetime(2026, 8, 1)


class ChainStub:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.filters = []

    def filter(self, *a, **k):
        self.filters.append((a, k))
        return self

    def order_by(self, *a, **k):
        self.filters.append(("order_by", (a, k)))
        return self

    def group_by(self, *a, **k):
        return self

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, specialists=None, today_rows=None, active_rows=None):
        self.specialist_stub = ChainStub(specialists or [])
        self.today_stub = ChainStub(today_rows or [])
        self.active_stub = ChainStub(active_rows or [])
        self._conv_queries = 0

    def query(self, *entities):
        # 端点有单实体（Specialist）与多实体（列 + func 聚合）两种查询：
        # 从任一实体解析出表名即可分发
        name = None
        for ent in entities:
            table = getattr(ent, "__table__", None)
            if table is None:
                clause = next(iter(getattr(ent, "clauses", ())), None)
                table = getattr(clause, "table", None)
            name = getattr(table, "name", None) or getattr(ent, "__name__", None)
            if name:
                break
        if name == "digital_specialists":
            return self.specialist_stub
        if name == "conversations":
            # 两个聚合查询按调用顺序分发：第 1 次 → today 计数，第 2 次 → 最近活跃
            self._conv_queries += 1
            return self.today_stub if self._conv_queries == 1 else self.active_stub
        raise AssertionError(f"unexpected table: {name}")


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "role": "admin"}
    return TestClient(app)


def _reset_registry():
    registry._states.clear()


def test_live_status_working_from_registry(monkeypatch):
    from app.core import activity_registry
    monkeypatch.setattr(activity_registry, "_now", lambda: datetime(2026, 8, 6, 10, 0, 0))
    _reset_registry()
    registry.set_working(1, PHASE_GENERATING, "肺癌用药注意事项")
    db = FakeDb(
        specialists=[FakeSpecialist(1, "学术专员-肺癌", "active")],
        today_rows=[(1, 12)],
        active_rows=[(1, datetime(2026, 8, 6, 10, 0, 5))],
    )
    resp = _client(db).get("/api/v1/specialists/live-status")
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["items"][0]
    assert item["state"] == "working"
    assert item["phase"] == PHASE_GENERATING
    assert item["phase_text"] == "正在检索知识库并生成回答"
    assert item["question_snippet"] == "肺癌用药注意事项"
    assert item["today_conversations"] == 12
    assert resp.json()["data"]["summary"] == {"working": 1, "idle": 0, "offline": 0}


def test_live_status_idle_when_registry_empty_and_no_recent(monkeypatch):
    _reset_registry()
    db = FakeDb(
        specialists=[FakeSpecialist(1, "A", "active")],
        today_rows=[(1, 3)],
        active_rows=[(1, datetime(2026, 8, 5, 9, 0, 0))],  # 昨天，>5 分钟
    )
    resp = _client(db).get("/api/v1/specialists/live-status")
    item = resp.json()["data"]["items"][0]
    assert item["state"] == "idle"
    assert item["phase"] is None
    assert item["today_conversations"] == 3


def test_live_status_recent_conversation_degrades_to_working(monkeypatch):
    from app.core import activity_registry as ar
    base = datetime(2026, 8, 6, 10, 0, 0)
    monkeypatch.setattr(ar, "_now", lambda: base + timedelta(seconds=10))
    monkeypatch.setattr(ar, "STARTED_AT", base)
    _reset_registry()
    db = FakeDb(
        specialists=[FakeSpecialist(1, "A", "active")],
        today_rows=[],
        active_rows=[(1, datetime.utcnow() - timedelta(minutes=1))],  # 1 分钟前
    )
    resp = _client(db).get("/api/v1/specialists/live-status")
    item = resp.json()["data"]["items"][0]
    assert item["state"] == "working"
    assert item["phase"] == PHASE_GENERATING  # 降级粗粒度
    assert item["question_snippet"] is None


def test_live_status_recent_conversation_idle_when_not_recently_started(monkeypatch):
    from datetime import datetime, timedelta
    from app.core import activity_registry as ar
    from app.core.activity_registry import registry as reg
    reg._states.clear()
    base = datetime(2026, 8, 6, 10, 0, 0)
    monkeypatch.setattr(ar, "_now", lambda: base + timedelta(minutes=30))
    monkeypatch.setattr(ar, "STARTED_AT", base)
    db = FakeDb(
        specialists=[FakeSpecialist(1, "A", "active")],
        today_rows=[],
        active_rows=[(1, datetime.utcnow() - timedelta(minutes=1))],
    )
    resp = _client(db).get("/api/v1/specialists/live-status")
    item = resp.json()["data"]["items"][0]
    assert item["state"] == "idle"
    assert resp.json()["data"]["summary"] == {"working": 0, "idle": 1, "offline": 0}


def test_live_status_disabled_is_offline_even_with_registry_entry(monkeypatch):
    _reset_registry()
    registry.set_working(2, PHASE_GENERATING, "q")
    db = FakeDb(
        specialists=[
            FakeSpecialist(1, "A", "active"),
            FakeSpecialist(2, "B", "disabled"),
            FakeSpecialist(3, "C", "draft"),
        ],
        today_rows=[], active_rows=[],
    )
    resp = _client(db).get("/api/v1/specialists/live-status")
    by_id = {i["id"]: i for i in resp.json()["data"]["items"]}
    assert by_id[1]["state"] == "idle"
    assert by_id[2]["state"] == "offline"
    assert by_id[3]["state"] == "offline"
    assert resp.json()["data"]["summary"] == {"working": 0, "idle": 1, "offline": 2}


def test_live_status_requires_auth():
    # 先清掉其它用例注入的依赖替身，回到真实认证链路
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    # HTTPBearer 无 Authorization 头 → 403（缺头 403，无效 token 才是 401；
    # 与既有 /specialists 系列受保护路由行为一致）
    resp = TestClient(app).get("/api/v1/specialists/live-status")
    assert resp.status_code == 403
