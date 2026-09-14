"""
认证服务单元测试

覆盖重点是安全属性，不只是"能登录"：
  - 验证码一次性、有过期、有尝试次数上限、有重发冷却
  - 未设置密码的账号不能密码登录
  - 停用账号不能登录、不能用旧 token 取 profile
  - 存储不可用时不放行（fail-closed）
  - 错误信息不区分"用户不存在"和"凭证错误"
  - 用户管理端点防提权：role 变更仅限 admin、禁止自改 role/status、
    停用/降级即时生效（旧 token 也以库为准）

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
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
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

# SQLite 只对 INTEGER PRIMARY KEY 自增，而模型主键是 BigInteger（PG 的
# BIGSERIAL）。在 SQLite 方言下把 BigInteger 编译成 INTEGER，API 创建用户时
# 才能拿到自增 id（显式给 id 的 fixture 行不受影响，PG 编译路径也不受影响）。
@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


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

    def in_cooldown(self, phone, scene="login"):
        raise CodeStoreError("redis down")

    def save(self, phone, code, ttl, cooldown, scene="login"):
        raise CodeStoreError("redis down")

    def consume(self, phone, code, max_attempts, scene="login"):
        raise CodeStoreError("redis down")

    def drop(self, phone, scene="login"):
        raise CodeStoreError("redis down")

    def daily_count(self, phone):
        raise CodeStoreError("redis down")

    def bump_daily(self, phone):
        raise CodeStoreError("redis down")


store = MemoryCodeStore()
sender = RecordingSender()
_lock_guard = None   # M9：MemoryLoginGuard 实例，fixture 内延迟初始化


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_db
app.dependency_overrides[get_code_store] = lambda: store
app.dependency_overrides[get_sender] = lambda: sender


@pytest.fixture(autouse=True)
def _reset_daily_limit():
    """滚动日限（默认 10 条/号/24h）是产品行为，本文件不测它——
    但整文件共用一个 store，十几个发码用例会累积触顶，把后面的用例
    一起拖死。每用例清空日限计数（冷却/验证码键不动，各自的用例自理）。"""
    store._daily.clear()
    yield

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
        # M9 锁定测试专用：独立账号，避免锁死后污染 rep01 的其余用例
        User(id=99, username="lockuser", full_name="锁定测试", phone="13800000099",
             role="rep", status="active", password_hash=hash_password(PASSWORD)),
    ])
    db.commit()
    db.close()

    # M9：每测试重置登录锁定计数（login_guard 未实现时本批尚未接线，跳过）
    global _lock_guard
    try:
        from app.core.login_guard import MemoryLoginGuard
        import app.api.auth as _auth_api
        if _lock_guard is None:
            _lock_guard = MemoryLoginGuard(max_failures=5, lockout_seconds=900)
        _lock_guard.clear()
        _dep = getattr(_auth_api, "get_login_guard", None)
        if _dep is not None:
            app.dependency_overrides[_dep] = lambda: _lock_guard
    except ImportError:
        pass

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

    def test_非dict_body返回参数错误(self):
        """A3：JSON 数组等非对象 body → 4xx code 1000（FastAPI 预校验 422 或
        端点 isinstance 校验 400），绝不落 AttributeError 500"""
        r = client.post("/api/v1/auth/send-code", json=["13800000001"])
        assert r.status_code in (400, 422)
        assert r.json()["code"] == 1000

    def test_验证码键已存在时save返回False按冷却处理(self):
        """A9：冷却检查与 save 之间的竞态——冷却键被绕过（如并发后到者）但
        验证码键仍在存时，save 的 SET NX 返回 False → 按冷却 4002 处理，
        先发验证码不被覆盖（用户拿到的码仍然有效）"""
        _send_code(ACTIVE_PHONE)
        code = _issued_code(ACTIVE_PHONE)
        # 模拟并发后到者：冷却键已过期/被清，但验证码键还在存
        store._cooldowns.clear()
        r = _send_code(ACTIVE_PHONE)
        assert r.status_code == 422
        assert r.json()["code"] == 4002
        # 后到者没有覆盖先发码：真实短信只发了一条，且先发码仍可登录
        assert len(sender.sent) == 1
        r2 = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": code})
        assert r2.status_code == 200

    def test_审计request_id用中间件校验值而非原始头(self, monkeypatch):
        """A6：写审计的 request_id 取 RequestIDMiddleware 校验过的上下文值——
        超长原始头会被中间件换成新 UUID，不再把 300 字符的原始头塞进审计列
        （列长 100，超长会 DataError 整条失败、审计 write 异常被吞 = 抹掉自己）"""
        import app.api.auth as auth_api

        calls = []

        async def fake_write(**kw):
            calls.append(kw)

        monkeypatch.setattr(auth_api, "write_audit_log", fake_write)
        huge = "x" * 300
        r = client.post("/api/v1/auth/send-code",
                        json={"phone": ACTIVE_PHONE},
                        headers={"X-Request-ID": huge})
        assert r.status_code == 200
        assert len(calls) == 1
        rid = calls[0].get("request_id")
        assert rid is not None and rid != huge
        assert len(rid) <= 100

    def test_未知手机号在aliyun通道下做等时长延迟补偿(self, monkeypatch):
        """A7：aliyun 通道下未注册手机号不发短信、响应比正常路径快一个网络
        往返，用固定延迟拉平耗时特征（缓解非根治）。console 通道不补偿。"""
        import app.api.auth as auth_api

        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(auth_api.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(auth_api.settings, "SMS_PROVIDER", "aliyun")
        assert _send_code(UNKNOWN_PHONE).status_code == 200
        assert sleeps == [0.2]

        # console 通道（本地/CI）无真实网络发送，不补偿
        sleeps.clear()
        store._cooldowns.clear()
        monkeypatch.setattr(auth_api.settings, "SMS_PROVIDER", "console")
        assert _send_code(UNKNOWN_PHONE).status_code == 200
        assert sleeps == []


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

    def test_同一验证码并发登录只有一个成功(self):
        """H1 回归：两个并发请求携带同一正确码，只有一个能签出 token。
        比较与作废已收进 store.consume 的原子操作（修复前 take_attempt →
        Python 比较 → drop 三次独立调用之间存在竞态，两个并发请求都能通过）。"""
        import asyncio

        import httpx

        _send_code(ACTIVE_PHONE)
        body = {"phone": ACTIVE_PHONE, "code": _issued_code(ACTIVE_PHONE)}

        async def login():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                return (await ac.post("/api/v1/auth/login", json=body)).status_code

        async def run():
            return await asyncio.gather(login(), login())

        assert sorted(asyncio.run(run())) == [200, 401]

    def test_错误验证码被拒(self):
        _send_code(ACTIVE_PHONE)
        r = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": "000000"})
        assert r.status_code == 401
        assert r.json()["code"] == 2000

    def test_没发过码直接登录被拒(self):
        r = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": "123456"})
        assert r.status_code == 401

    def test_尝试次数用尽后验证码作废(self):
        """5 次全错 → 验证码作废，第 6 次起任何输入（包括正确码）都被拒"""
        _send_code(ACTIVE_PHONE)
        real_code = _issued_code(ACTIVE_PHONE)
        for _ in range(5):
            assert client.post("/api/v1/auth/login",
                               json={"phone": ACTIVE_PHONE, "code": "000000"}).status_code == 401
        # 第 6 次输对也进 exhausted，且文案与通用登录失败一致
        r = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": real_code})
        assert r.status_code == 401
        assert r.json()["message"] == "手机号或验证码错误"

    def test_第5次输对验证码仍可登录(self):
        """上限内（含第 5 次）输对验证码应放行 —— 回归 off-by-one"""
        _send_code(ACTIVE_PHONE)
        real_code = _issued_code(ACTIVE_PHONE)
        for _ in range(4):
            assert client.post("/api/v1/auth/login",
                               json={"phone": ACTIVE_PHONE, "code": "000000"}).status_code == 401
        r = client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": real_code})
        assert r.status_code == 200
        assert r.json()["data"]["token"]

    def test_用尽后与通用登录失败响应文案一致(self):
        """exhausted 只会发生在"已注册且验证码在存"，文案差异会泄露注册状态"""
        _send_code(ACTIVE_PHONE)
        for _ in range(5):
            client.post("/api/v1/auth/login", json={"phone": ACTIVE_PHONE, "code": "000000"})
        exhausted = client.post("/api/v1/auth/login",
                                json={"phone": ACTIVE_PHONE, "code": "000000"})
        generic = client.post("/api/v1/auth/login", json={"phone": UNKNOWN_PHONE, "code": "000000"})
        assert exhausted.json()["message"] == generic.json()["message"]
        assert "次数过多" not in exhausted.json()["message"]

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

    def test_错误密码登录写失败审计(self, monkeypatch):
        """合规硬伤回归：登录失败必须留痕，且审计内容绝不包含密码本身"""
        import app.api.auth as auth_api

        calls = []

        async def fake_write(**kw):
            calls.append(kw)

        monkeypatch.setattr(auth_api, "write_audit_log", fake_write)
        r = client.post("/api/v1/auth/login", json={"username": "rep01", "password": "wrong"})
        assert r.status_code == 401
        failed = [c for c in calls if c.get("action") == "auth_login_failed"]
        assert len(failed) == 1, calls
        after = failed[0]["after_value"]
        assert after["method"] == "password"
        assert after["username"] == "rep01"
        assert "password" not in after
        assert "wrong" not in str(after)

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

    def test_非dict_body返回参数错误(self):
        """A3：JSON 数组等非对象 body → 4xx code 1000（FastAPI 预校验 422 或
        端点 isinstance 校验 400），绝不落 AttributeError 500"""
        r = client.post("/api/v1/auth/login", json=["x"])
        assert r.status_code in (400, 422)
        assert r.json()["code"] == 1000

    def test_不存在与未设密码路径都执行bcrypt校验(self, monkeypatch):
        """A1 时序枚举防护：不测耗时（不稳定），改为断言"用户不存在"与
        "未设密码"两条秒回路径都补执行了一次真实 bcrypt 校验（dummy hash），
        与"密码错误"路径耗时同量级，防响应时间探测账号存在性"""
        import app.api.auth as auth_api

        real_verify = auth_api.verify_password
        calls = []

        def spy(password, hashed):
            calls.append((password, hashed))
            return real_verify(password, hashed)

        monkeypatch.setattr(auth_api, "verify_password", spy)
        r1 = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "wrong"})
        r2 = client.post("/api/v1/auth/login", json={"username": "nopwd", "password": "wrong"})
        assert r1.status_code == r2.status_code == 401
        assert r1.json()["message"] == r2.json()["message"]
        # 两条路径各执行了一次校验，且都打在 dummy hash 上（真实比对是幌子）
        assert len(calls) == 2, calls
        assert all(h == auth_api._DUMMY_PASSWORD_HASH for _, h in calls)


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


# ==================== 用户管理安全（防提权 / 防自锁死 / 停用即时生效） ====================

class TestUserManagementSecurity:
    """users 端点安全回归：role 变更仅限 admin、禁止自改 role/status、
    停用/降级即时生效（持有未过期 token 也以库为准，返回 403 code 3000）。"""

    @pytest.fixture()
    def seeded_managers(self, fresh_state):
        """在基础 3 个用户（id 1-3）之外补 admin 与两个 manager（显式 id）"""
        db = TestSession()
        db.add_all([
            User(id=10, username="admin01", full_name="管理员", phone="13800000010",
                 role="admin", status="active", password_hash=hash_password(PASSWORD)),
            User(id=11, username="mgr01", full_name="经理一", phone="13800000011",
                 role="manager", status="active", password_hash=hash_password(PASSWORD)),
            User(id=12, username="mgr02", full_name="经理二", phone="13800000012",
                 role="manager", status="active", password_hash=hash_password(PASSWORD)),
        ])
        db.commit()
        db.close()
        yield

    def _auth(self, username):
        r = client.post("/api/v1/auth/login",
                        json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['data']['token']}"}

    def test_manager不能创建admin账号(self, seeded_managers):
        """manager 创建用户时传 role=admin → 403 code 3000，且用户不应被创建"""
        r = client.post("/api/v1/users", headers=self._auth("mgr01"),
                        json={"username": "mgr_makes_admin", "full_name": "新管理员",
                              "role": "admin"})
        assert r.status_code == 403
        assert r.json()["code"] == 3000
        db = TestSession()
        try:
            assert db.query(User).filter(User.username == "mgr_makes_admin").first() is None
        finally:
            db.close()

    def test_manager传任何role都拒绝(self, seeded_managers):
        """manager 传 role 一律拒绝，不只是 admin：传 manager/rep 同样 403"""
        for role in ("manager", "rep"):
            r = client.post("/api/v1/users", headers=self._auth("mgr01"),
                            json={"username": f"mgr_makes_{role}", "full_name": "新员工",
                                  "role": role})
            assert r.status_code == 403, f"role={role}"
            assert r.json()["code"] == 3000

    def test_manager不传role可创建默认rep(self, seeded_managers):
        """manager 不碰 role 字段时原有能力保留：创建默认 rep 成功"""
        r = client.post("/api/v1/users", headers=self._auth("mgr01"),
                        json={"username": "mgr_makes_rep", "full_name": "新代表"})
        assert r.status_code == 200
        assert r.json()["data"]["role"] == "rep"

    def test_manager不能把自己role改成admin(self, seeded_managers):
        """水平提权路径：manager 把自己 role 改成 admin → 403 code 3000"""
        r = client.put("/api/v1/users/11", headers=self._auth("mgr01"),
                       json={"role": "admin"})
        assert r.status_code == 403
        assert r.json()["code"] == 3000

    def test_manager不能改别人的role(self, seeded_managers):
        """manager 把别的 manager 改成 admin 同样被拒"""
        r = client.put("/api/v1/users/12", headers=self._auth("mgr01"),
                       json={"role": "admin"})
        assert r.status_code == 403
        assert r.json()["code"] == 3000

    def test_admin可以把manager提升为admin(self, seeded_managers):
        """正向：admin 改别人的 role 不受限"""
        r = client.put("/api/v1/users/11", headers=self._auth("admin01"),
                       json={"role": "admin"})
        assert r.status_code == 200
        assert r.json()["data"]["role"] == "admin"

    def test_admin也不能改自己role或status(self, seeded_managers):
        """任何人（含 admin）都不能改自己的 role/status：防误操作自锁死"""
        h = self._auth("admin01")
        for body in ({"role": "manager"}, {"status": "disabled"}):
            r = client.put("/api/v1/users/10", headers=h, json=body)
            assert r.status_code == 403, body
            assert r.json()["code"] == 3000

    def test_admin可以停用别人(self, seeded_managers):
        """正向：admin 停用别人不受限（改别人 status 允许）"""
        r = client.put("/api/v1/users/11", headers=self._auth("admin01"),
                       json={"status": "disabled"})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "disabled"

    def test_status只接受active或disabled(self, seeded_managers):
        """status 枚举校验：其他值 → 400 ParamError"""
        r = client.put("/api/v1/users/11", headers=self._auth("admin01"),
                       json={"status": "banned"})
        assert r.status_code == 400
        assert r.json()["code"] == 1000

    def test_被停用用户持旧token调users端点被拒(self, seeded_managers):
        """停用即时生效：被停用用户拿未过期 token 调 users 端点 → 401 code 2003

        H2（2026-08-11）起 get_current_user 实时查库，停用账号在角色校验前即被
        拒绝（未认证 401），语义比原 403「无权限」更准确；库中已无该 active 用户"""
        h = self._auth("mgr01")
        db = TestSession()
        db.query(User).filter(User.username == "mgr01").update({"status": "disabled"})
        db.commit()
        db.close()
        r = client.get("/api/v1/users", headers=h)
        assert r.status_code == 401
        # get_current_user 抛 HTTPException(detail={code:2003,...})；
        # S1（2026-08-13）起 shared 异常处理器把含 code 的 detail 原样平铺成
        # {code, message, data}，不再套 FastAPI 默认的 {detail: {...}}
        assert r.json()["code"] == 2003

    def test_被降级用户持旧token调users端点被拒(self, seeded_managers):
        """降级即时生效：库中 role 与 token 声明不一致 → 403，以库为准"""
        h = self._auth("mgr01")
        db = TestSession()
        db.query(User).filter(User.username == "mgr01").update({"role": "rep"})
        db.commit()
        db.close()
        r = client.put("/api/v1/users/12", headers=h, json={"full_name": "改名"})
        assert r.status_code == 403
        assert r.json()["code"] == 3000

    def test_create重复手机号返回4001不落500(self, seeded_managers):
        """A2：手机号查重预检（BusinessError 4001），替代 commit 时撞唯一索引
        uq_users_phone 的 IntegrityError 500。手机号是登录凭据，重复会劫持
        验证码登录通道"""
        r = client.post("/api/v1/users", headers=self._auth("admin01"),
                        json={"username": "dup_phone", "full_name": "重复手机号",
                              "phone": ACTIVE_PHONE})
        # 业务错误码 4001 按共享异常处理器映射为 HTTP 422（非 500 即达修复目的）
        assert r.status_code == 422
        assert r.json()["code"] == 4001
        db = TestSession()
        try:
            assert db.query(User).filter(User.username == "dup_phone").first() is None
        finally:
            db.close()

    def test_create坏manager_id返回1000不落500(self, seeded_managers):
        """A2：manager_id 存在性预检（ParamError 1000），替代 commit 时外键
        约束的 IntegrityError 500；非整数同样 1000"""
        h = self._auth("admin01")
        for bad in (99999, "not-an-int"):
            r = client.post("/api/v1/users", headers=h,
                            json={"username": "bad_mgr", "full_name": "坏经理",
                                  "manager_id": bad})
            assert r.status_code == 400, bad
            assert r.json()["code"] == 1000

    def test_update重复手机号返回4001不落500(self, seeded_managers):
        """A2：更新手机号查重（排除自身）——撞唯一索引前拦成 4001"""
        r = client.put("/api/v1/users/12", headers=self._auth("admin01"),
                       json={"phone": ACTIVE_PHONE})
        # 业务错误码 4001 按共享异常处理器映射为 HTTP 422（非 500 即达修复目的）
        assert r.status_code == 422
        assert r.json()["code"] == 4001

    def test_update坏manager_id返回1000不落500(self, seeded_managers):
        """A2：更新 manager_id 预检存在性——不存在的 id 与非整数都 1000"""
        h = self._auth("admin01")
        for bad in (99999, "not-an-int"):
            r = client.put("/api/v1/users/12", headers=h, json={"manager_id": bad})
            assert r.status_code == 400, bad
            assert r.json()["code"] == 1000

    def test_update合法manager_id可变更(self, seeded_managers):
        """A2 正向：manager_id 进更新白名单，合法变更不受预检影响"""
        r = client.put("/api/v1/users/12", headers=self._auth("admin01"),
                       json={"manager_id": 11})
        assert r.status_code == 200

    def test_create非dict_body返回参数错误(self, seeded_managers):
        """A3：JSON 数组等非对象 body → 4xx code 1000（FastAPI 预校验 422 或
        端点 isinstance 校验 400），绝不落 AttributeError 500"""
        r = client.post("/api/v1/users", headers=self._auth("admin01"), json=[1, 2])
        assert r.status_code in (400, 422)
        assert r.json()["code"] == 1000


# ==================== 密码登录失败锁定（M9，2026-08-21 审计） ====================

class TestLoginByPasswordLockout:
    """验证码路径自带单码尝试上限；密码路径此前无锁定——连续错密必须锁号。
    定窗语义：第一次错密起 15 分钟内累计 5 次 → 锁 15 分钟，正确密码也拒。"""

    def _post(self, password):
        return client.post("/api/v1/auth/login",
                           json={"username": "lockuser", "password": password})

    def _require_m9_wired(self):
        import app.api.auth as auth_api
        if getattr(auth_api, "get_login_guard", None) is None:
            pytest.fail("M9 未接线：login 端点缺少 get_login_guard 依赖")

    def test_连续错密达到阈值后_正确密码也被锁拒(self):
        self._require_m9_wired()
        for _ in range(5):
            assert self._post("totally-wrong").status_code == 401
        r = self._post(PASSWORD)   # 密码完全正确，但账号已锁
        assert r.status_code == 401
        assert "锁" in (r.json().get("message") or ""), r.json()

    def test_未达阈值_正确密码可登录且计数清零(self):
        self._require_m9_wired()
        for _ in range(4):
            assert self._post("totally-wrong").status_code == 401
        assert self._post(PASSWORD).status_code == 200
        for _ in range(4):         # 成功已清零：再错 4 次不会锁
            assert self._post("totally-wrong").status_code == 401
        assert self._post(PASSWORD).status_code == 200
