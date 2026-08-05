"""
认证服务单元测试

覆盖重点是安全属性，不只是"能登录"：
  - 验证码一次性、有过期、有尝试次数上限、有重发冷却
  - 未设置密码的账号不能密码登录
  - 停用账号不能登录、不能用旧 token 取 profile
  - 存储不可用时不放行（fail-closed）
  - 错误信息不区分"用户不存在"和"凭证错误"

不依赖真实 Redis / PostgreSQL：CodeStore 用内存实现，DB 用 SQLite。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 必须在 import app.main 之前设好，否则启动守卫会拒绝启动
os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.user import User

from app.api.auth import get_code_store, get_sender
from app.core.code_store import CodeStore, CodeStoreError, MemoryCodeStore
from app.core.security import hash_password
from app.main import app

# ---------- 测试替身 ----------

# StaticPool：内存 SQLite 每条连接都是独立的库，必须复用同一条连接，
# 否则 fixture 建的表在请求处理线程里看不到
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class RecordingSender:
    """记录发出的验证码，不真发短信"""

    def __init__(self):
        self.sent = []

    def send_code(self, phone, code):
        self.sent.append((phone, code))


class BrokenCodeStore(CodeStore):
    """模拟 Redis 挂掉"""

    def in_cooldown(self, phone):
        raise CodeStoreError("redis down")

    def save(self, phone, code, ttl, cooldown):
        raise CodeStoreError("redis down")

    def take_attempt(self, phone, max_attempts):
        raise CodeStoreError("redis down")

    def drop(self, phone):
        raise CodeStoreError("redis down")


store = MemoryCodeStore()
sender = RecordingSender()


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_db
app.dependency_overrides[get_code_store] = lambda: store
app.dependency_overrides[get_sender] = lambda: sender

client = TestClient(app)

ACTIVE_PHONE = "13800000001"
NOPWD_PHONE = "13800000002"
DISABLED_PHONE = "13800000003"
UNKNOWN_PHONE = "13900000009"
PASSWORD = "Str0ng-Pass!"


@pytest.fixture(autouse=True)
def fresh_state():
    """每个用例重建库和验证码存储

    只建 users 表：shared.models 里其他表用了 PostgreSQL 的 JSONB，SQLite 渲染不了；
    认证服务也只读写 users。
    """
    only_users = [User.__table__]
    Base.metadata.drop_all(engine, tables=only_users)
    Base.metadata.create_all(engine, tables=only_users)
    db = TestSession()
    # 显式给 id：TimestampMixin 用 BigInteger 主键，SQLite 只对 INTEGER PRIMARY KEY 自增
    # （PostgreSQL 下是 BIGSERIAL，正常自增，这里只是测试环境的适配）
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone=ACTIVE_PHONE, role="rep",
             status="active", password_hash=hash_password(PASSWORD)),
        User(id=2, username="nopwd", full_name="未设密码", phone=NOPWD_PHONE, role="rep",
             status="active", password_hash=None),
        User(id=3, username="disabled", full_name="已停用", phone=DISABLED_PHONE, role="rep",
             status="disabled", password_hash=hash_password(PASSWORD)),
    ])
    db.commit()
    db.close()

    store._codes.clear()
    store._cooldowns.clear()
    sender.sent.clear()
    app.dependency_overrides[get_code_store] = lambda: store
    yield


def _send_code(phone):
    return client.post("/api/v1/auth/send-code", json={"phone": phone})


def _issued_code(phone):
    """从替身发送器里取出实际下发的验证码"""
    return next(code for p, code in sender.sent if p == phone)


# ==================== 发送验证码 ====================

class TestSendCode:
    def test_已注册手机号能拿到验证码(self):
        r = _send_code(ACTIVE_PHONE)
        assert r.status_code == 200
        assert r.json()["data"]["expire_seconds"] == 300
        assert len(sender.sent) == 1

    def test_手机号格式错误返回参数错误(self):
        r = _send_code("12345")
        assert r.status_code == 400
        assert r.json()["code"] == 1000

    def test_重发受冷却限制(self):
        assert _send_code(ACTIVE_PHONE).status_code == 200
        r = _send_code(ACTIVE_PHONE)
        assert r.status_code == 422
        assert r.json()["code"] == 4002

    def test_未注册手机号不发短信但响应一致(self):
        """不能用 send-code 枚举账号"""
        ok = _send_code(ACTIVE_PHONE)
        store._cooldowns.clear()
        unknown = _send_code(UNKNOWN_PHONE)
        assert unknown.status_code == ok.status_code == 200
        assert unknown.json()["data"]["expire_seconds"] == ok.json()["data"]["expire_seconds"]
        # 真实短信只发给已注册用户
        assert [p for p, _ in sender.sent] == [ACTIVE_PHONE]

    def test_停用账号不下发验证码(self):
        assert _send_code(DISABLED_PHONE).status_code == 200
        assert sender.sent == []

    def test_存储不可用时不放行(self):
        """Redis 挂了必须报错，不能静默继续"""
        app.dependency_overrides[get_code_store] = lambda: BrokenCodeStore()
        r = _send_code(ACTIVE_PHONE)
        assert r.status_code == 500
        assert r.json()["code"] == 5004


# ==================== 验证码登录 ====================

class TestLoginByCode:
    def test_正确验证码可登录并返回token和用户(self):
        _send_code(ACTIVE_PHONE)
        r = client.post("/api/v1/auth/login",
                        json={"phone": ACTIVE_PHONE, "code": _issued_code(ACTIVE_PHONE)})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["token"]
        assert data["user"]["username"] == "rep01"
        # 前端读的是 name 字段
        assert data["user"]["name"] == "张代表"
        # 绝不能把密码哈希带出去
        assert "password_hash" not in data["user"]

    def test_验证码是一次性的(self):
        _send_code(ACTIVE_PHONE)
        code = _issued_code(ACTIVE_PHONE)
        body = {"phone": ACTIVE_PHONE, "code": code}
        assert client.post("/api/v1/auth/login", json=body).status_code == 200
        # 同一验证码重放必须失败
        assert client.post("/api/v1/auth/login", json=body).status_code == 401

    def test_错误验证码被拒(self):
        _send_code(ACTIVE_PHONE)
        r = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": "000000"})
        assert r.status_code == 401
        assert r.json()["code"] == 2000

    def test_没发过码直接登录被拒(self):
        r = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": "123456"})
        assert r.status_code == 401

    def test_尝试次数用尽后验证码作废(self):
        _send_code(ACTIVE_PHONE)
        real_code = _issued_code(ACTIVE_PHONE)
        for _ in range(4):
            client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": "000000"})
        # 第 5 次触发上限
        r = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": "000000"})
        assert r.status_code == 401
        assert "次数过多" in r.json()["message"]
        # 此后即使输对了也不行
        assert client.post("/api/v1/auth/login",
                           json={"phone": ACTIVE_PHONE, "code": real_code}).status_code == 401

    def test_未注册手机号与错误验证码返回同样的信息(self):
        """错误信息不能泄露账号是否存在"""
        _send_code(ACTIVE_PHONE)
        wrong = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": "000000"})
        unknown = client.post("/api/v1/auth/login", json={"phone": UNKNOWN_PHONE, "code": "000000"})
        assert wrong.json()["message"] == unknown.json()["message"]

    def test_存储不可用时不放行(self):
        app.dependency_overrides[get_code_store] = lambda: BrokenCodeStore()
        r = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": "123456"})
        assert r.status_code == 500


# ==================== 密码登录 ====================

class TestLoginByPassword:
    def test_正确密码可登录(self):
        r = client.post("/api/v1/auth/login", json={"username": "rep01", "password": PASSWORD})
        assert r.status_code == 200
        assert r.json()["data"]["token"]

    def test_错误密码被拒(self):
        r = client.post("/api/v1/auth/login", json={"username": "rep01", "password": "wrong"})
        assert r.status_code == 401

    def test_未设置密码的账号不能密码登录(self):
        """password_hash 为 NULL 时不能被空密码/任意密码绕过"""
        for pwd in ["", "anything", PASSWORD]:
            r = client.post("/api/v1/auth/login", json={"username": "nopwd", "password": pwd})
            assert r.status_code in (400, 401), f"密码 {pwd!r} 竟然通过了"

    def test_停用账号不能登录(self):
        r = client.post("/api/v1/auth/login", json={"username": "disabled", "password": PASSWORD})
        assert r.status_code == 401

    def test_不存在的用户与错误密码返回同样的信息(self):
        a = client.post("/api/v1/auth/login", json={"username": "rep01", "password": "wrong"})
        b = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong"})
        assert a.json()["message"] == b.json()["message"]

    def test_两种方式都不给则报参数错误(self):
        r = client.post("/api/v1/auth/login", json={})
        assert r.status_code == 400
        assert r.json()["code"] == 1000


# ==================== 当前用户 ====================

class TestCurrentUser:
    def _token(self, username="rep01"):
        r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        return r.json()["data"]["token"]

    def test_profile_和_me_返回一致(self):
        h = {"Authorization": f"Bearer {self._token()}"}
        p = client.get("/api/v1/auth/profile", headers=h)
        m = client.get("/api/v1/auth/me", headers=h)
        assert p.status_code == m.status_code == 200
        assert p.json()["data"] == m.json()["data"]
        assert p.json()["data"]["username"] == "rep01"

    def test_无token被拒(self):
        # 具体码取决于 FastAPI 版本：0.115 的 HTTPBearer 缺凭证给 403，
        # 0.13x 改成了语义更准的 401。这里只断言"必须被拒"。
        assert client.get("/api/v1/auth/profile").status_code in (401, 403)

    def test_伪造token被拒(self):
        r = client.get("/api/v1/auth/profile",
                       headers={"Authorization": "Bearer not.a.real.token"})
        assert r.status_code == 401

    def test_登录后被停用则旧token立即失效(self):
        """token 只是入场券，用户状态以库为准"""
        token = self._token()
        db = TestSession()
        db.query(User).filter(User.username == "rep01").update({"status": "disabled"})
        db.commit()
        db.close()
        r = client.get("/api/v1/auth/profile", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
