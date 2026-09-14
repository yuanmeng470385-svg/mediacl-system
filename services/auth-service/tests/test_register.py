"""医生自助注册（部署挂账 §5）：POST /api/v1/auth/register

覆盖：
  - 注册成功：建 doctor 用户（username=phone、active、bcrypt）+ token 可直接用
  - 医院信息落 hcps 档案表；不填医院信息不建 hcps 行
  - 重复手机号 400；弱密码/纯数字密码 400；姓名过短 400；手机号格式 400

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

from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.hcp import Hcp
from shared.models.user import User

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
STRONG_PWD = "Test@2026a"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    # 不做模块级 dependency_overrides（会覆盖 test_auth 的同名设置、污染整个套件），
    # 照 test_exams.py 惯例在 fixture 内 setitem，用例结束自动还原
    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    Base.metadata.drop_all(engine, tables=TABLES)
    Base.metadata.create_all(engine, tables=TABLES)
    db = TestSession()
    db.add(User(id=1, username="13800000001", full_name="张医生", phone="13800000001",
                role="doctor", status="active"))
    db.commit()
    db.close()
    yield


def _body(**overrides):
    base = {"phone": NEW_PHONE, "full_name": "测试注册", "password": STRONG_PWD}
    base.update(overrides)
    return base


def test_register_success_creates_doctor_and_token():
    resp = client.post("/api/v1/auth/register", json=_body(hospital="协和医院", department="心内科", title="主治医师"))
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


def test_register_without_hospital_info_skips_hcp_row():
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 200, resp.text
    db = TestSession()
    assert db.query(Hcp).filter(Hcp.phone == NEW_PHONE).count() == 0
    db.close()


def test_register_token_works_for_authed_endpoint(monkeypatch):
    """注册即登录：返回的 token 能直接取 profile"""
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["token"]

    # profile 依赖 get_current_user（JWT 签发用同一 JWT_SECRET，可验）
    monkeypatch.setitem(
        app.dependency_overrides, get_current_user,
        lambda: {"id": 1, "username": "x", "role": "doctor"},
    )
    resp = client.get("/api/v1/auth/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_register_duplicate_phone_422():
    # 4001 与 users.py 创建用户撞号同码；HTTP 映射 422（BusinessError 非 4000 段）
    resp = client.post("/api/v1/auth/register", json=_body(phone="13800000001"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001
    assert resp.json()["message"] == "该手机号已注册，请直接登录"


def test_register_duplicate_after_own_registration_422():
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 200
    resp = client.post("/api/v1/auth/register", json=_body())
    assert resp.status_code == 422
    assert resp.json()["message"] == "该手机号已注册，请直接登录"


def test_register_weak_passwords_400():
    for pwd in ["short1a", "12345678", "abcdefgh", ""]:
        resp = client.post("/api/v1/auth/register", json=_body(password=pwd))
        assert resp.status_code == 400, pwd
        assert "密码" in resp.json()["message"]


def test_register_invalid_phone_or_name_400():
    assert client.post("/api/v1/auth/register", json=_body(phone="12345")).status_code == 400
    assert client.post("/api/v1/auth/register", json=_body(full_name="张")).status_code == 400
    assert client.post("/api/v1/auth/register", json=_body(full_name="张" * 31)).status_code == 400
