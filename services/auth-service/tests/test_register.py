"""医生自助注册（部署挂账 §5 → 2026-09-14 验证码制）：POST /api/v1/auth/register
与 send-code 的 scene=register 注册场景。

覆盖：
  - 注册成功：建 doctor 用户（username=phone、active）+ token 真验可用（profile 不 stub）
  - 密码选填：不填则 password_hash 为 None（只能验证码登录）；填了才校验强度
  - 验证码核销：错码 400、5 次错码用尽后正码也 400、登录场景的码不通用
  - send-code scene=register：未注册号发码（dev 模式回传）、已注册号 4001 提示
    直接登录、login 场景对未注册号仍静默、非法场景 400、60s 冷却、滚动日限
  - 重复手机号 4001/422；弱密码/纯数字密码 400；姓名过短 400；手机号格式 400

基建照 test_auth.py：SQLite 内存库 + dependency_overrides；hcps 表含 JSONB
列，SQLite 方言下编译为 JSON（specialist 测试同款惯例）。
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.hcp import Hcp
from shared.models.user import User

from app.api.auth import get_code_store, get_sender
from app.core.code_store import SCENE_LOGIN, SCENE_REGISTER, MemoryCodeStore
from app.main import app


# SQLite：BigInteger→INTEGER（自增主键）、JSONB→JSON（照 specialist 测试惯例）
@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "JSON"


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

TABLES = [User.__table__, Hcp.__table__]


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)

NEW_PHONE = "13900009931"
REG_CODE = "123456"


class _FakeSender:
    def __init__(self):
        self.sent = []

    def send_code(self, phone, code):
        self.sent.append((phone, code))


# fixture 内创建的 store/sender 挂到模块级holder，供 _issue/_send 简写
_holder: dict = {}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    store = MemoryCodeStore()
    sender = _FakeSender()
    _holder.update(store=store, sender=sender)
    # 不做模块级 dependency_overrides（会覆盖 test_auth 的同名设置、污染整个套件），
    # 照 test_exams.py 惯例在 fixture 内 setitem，用例结束自动还原
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    monkeypatch.setitem(app.dependency_overrides, get_code_store, lambda: store)
    monkeypatch.setitem(app.dependency_overrides, get_sender, lambda: sender)
    Base.metadata.drop_all(engine, tables=TABLES)
    Base.metadata.create_all(engine, tables=TABLES)
    db = TestSession()
    db.add(User(id=1, username="13800000001", full_name="张医生", phone="13800000001",
                role="doctor", status="active"))
    db.commit()
    db.close()
    yield


def _body(**overrides):
    base = {"phone": NEW_PHONE, "code": REG_CODE, "full_name": "测试注册"}
    base.update(overrides)
    return base


def _issue(phone: str = NEW_PHONE, code: str = REG_CODE, scene: str = SCENE_REGISTER):
    """直接向注入的 store 写一条验证码（绕过 60s 冷却，注册链路测试用）"""
    _holder["store"].save(phone, code, 300, 60, scene=scene)


def _send(phone: str, scene: str = None):
    payload = {"phone": phone}
    if scene:
        payload["scene"] = scene
    return client.post("/api/v1/auth/send-code", json=payload)


# ---------- 注册：验证码核销 ----------

def test_register_success_creates_doctor_and_token():
    _issue()
    resp = client.post(
        "/api/v1/auth/register",
        json=_body(password="Test@2026a", hospital="协和医院", department="心内科", title="主治医师"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["token"]
    assert data["user"]["role"] == "doctor"
    assert data["user"]["status"] == "active"
    assert data["user"]["username"] == NEW_PHONE

    db = TestSession()
    user = db.query(User).filter(User.phone == NEW_PHONE).one()
    assert user.password_hash  # bcrypt 已落库（to_dict 不含 hash，从库里验）
    hcp = db.query(Hcp).filter(Hcp.phone == NEW_PHONE).one()
    assert hcp.hospital == "协和医院"
    assert hcp.department == "心内科"
    assert hcp.title == "主治医师"
    db.close()


def test_register_token_works_for_authed_endpoint():
    """注册即登录：返回的 token 直接取 profile（get_current_user 真验 JWT+查库，不 stub）"""
    _issue()
    resp = client.post("/api/v1/auth/register", json=_body(password="Test@2026a"))
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["token"]
    resp = client.get("/api/v1/auth/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["phone"] == NEW_PHONE


def test_register_password_optional():
    """不填密码：注册成功且 password_hash 为 None（未设密码、禁止密码登录）"""
    _issue()
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 200, resp.text
    db = TestSession()
    user = db.query(User).filter(User.phone == NEW_PHONE).one()
    assert user.password_hash is None
    db.close()


def test_register_without_hospital_info_skips_hcp_row():
    _issue()
    resp = client.post("/api/v1/auth/register", json=_body(password="Test@2026a"))
    assert resp.status_code == 200, resp.text
    db = TestSession()
    assert db.query(Hcp).filter(Hcp.phone == NEW_PHONE).count() == 0
    db.close()


def test_register_missing_code_400():
    resp = client.post("/api/v1/auth/register", json=_body(code=""))
    assert resp.status_code == 400
    assert "验证码" in resp.json()["message"]


def test_register_wrong_code_400_then_correct_still_works():
    _issue()
    resp = client.post("/api/v1/auth/register", json=_body(code="000000"))
    assert resp.status_code == 400, resp.text
    assert resp.json()["message"] == "验证码错误或已过期，请重新获取"
    # 错一次只消耗一次尝试（上限 5），正码仍可用
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 200, resp.text


def test_register_code_exhausted_after_5_wrong_attempts():
    _issue()
    for _ in range(5):
        r = client.post("/api/v1/auth/register", json=_body(code="000000"))
        assert r.status_code == 400
    # 第 6 次带正码：验证码已作废
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 400
    assert "验证码" in resp.json()["message"]


def test_register_rejects_login_scene_code():
    """登录场景的验证码不能用于注册（键命名空间独立）"""
    _issue(scene=SCENE_LOGIN)
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 400
    assert "验证码" in resp.json()["message"]


def test_register_duplicate_phone_422():
    # 查重在验码之前：未发码也直接撞 4001（码是被真实发出的资源，不烧）
    resp = client.post("/api/v1/auth/register", json=_body(phone="13800000001"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
    assert resp.json()["message"] == "该手机号已注册，请直接登录"


def test_register_duplicate_after_own_registration_422():
    _issue()
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 200
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 422
    assert resp.json()["message"] == "该手机号已注册，请直接登录"


def test_register_weak_passwords_400():
    # 空串=不设密码属合法（test_register_password_optional 覆盖），这里只测填了弱密码
    _issue()
    for pwd in ["short1a", "12345678", "abcdefgh"]:
        resp = client.post("/api/v1/auth/register", json=_body(password=pwd))
        assert resp.status_code == 400, pwd
        assert "密码" in resp.json()["message"]


def test_register_invalid_phone_or_name_400():
    assert client.post("/api/v1/auth/register", json=_body(phone="12345")).status_code == 400
    assert client.post("/api/v1/auth/register", json=_body(full_name="张")).status_code == 400
    assert client.post("/api/v1/auth/register", json=_body(full_name="张" * 31)).status_code == 400


# ---------- send-code：注册场景 ----------

def test_send_code_register_scene_issues_code_and_registers():
    """全链路：scene=register 发码（dev 模式回传）→ 携码注册成功"""
    resp = _send(NEW_PHONE, scene=SCENE_REGISTER)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["expire_seconds"] > 0
    assert data["code"]  # AUTH_DEV_MODE=true 下回传
    assert _holder["sender"].sent and _holder["sender"].sent[-1][0] == NEW_PHONE

    resp = client.post("/api/v1/auth/register", json=_body(code=data["code"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["user"]["phone"] == NEW_PHONE


def test_send_code_register_scene_rejects_registered_phone():
    resp = _send("13800000001", scene=SCENE_REGISTER)
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
    assert resp.json()["message"] == "该手机号已注册，请直接登录"
    assert _holder["sender"].sent == []  # 未发码
    assert _holder["store"].daily_count("13800000001") == 0


def test_send_code_login_scene_still_silent_for_unregistered():
    """登录场景（默认）对未注册号仍静默成功不发码（防枚举，既有行为不变）"""
    resp = _send(NEW_PHONE)
    assert resp.status_code == 200
    assert "code" not in resp.json()["data"]
    assert _holder["sender"].sent == []
    # 没发过码，注册必失败
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 400


def test_send_code_invalid_scene_400():
    assert _send(NEW_PHONE, scene="reset").status_code == 400


def test_send_code_register_scene_cooldown():
    _issue()  # 写码带 60s 冷却（注册场景独立键）
    resp = _send(NEW_PHONE, scene=SCENE_REGISTER)
    assert resp.status_code == 422
    assert resp.json()["code"] == 4002


def test_send_code_daily_limit():
    # 滚动 24h 日限（跨场景按手机号累计）：到上限后再发被拒
    for _ in range(10):
        _holder["store"].bump_daily(NEW_PHONE)
    resp = _send(NEW_PHONE, scene=SCENE_REGISTER)
    assert resp.status_code == 422
    assert resp.json()["code"] == 4002
    assert "上限" in resp.json()["message"]


def test_memory_store_daily_count_shared_across_scenes():
    store = _holder["store"]
    store.bump_daily(NEW_PHONE)
    store.bump_daily(NEW_PHONE)
    assert store.daily_count(NEW_PHONE) == 2
