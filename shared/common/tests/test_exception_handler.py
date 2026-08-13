"""shared 异常处理器单测（S1，2026-08-13）

HTTPException / RequestValidationError 统一为 {code, message, data} 形状：
- detail 为 dict 且含 "code" → 按原语义平铺（保 auth 2001/2002/2003、internal_auth 3001）
- 其余裸 HTTPException → 按 status 映射 code，message 取 detail 字符串
- RequestValidationError → code 1000，message 带首条错误 loc

网关不注册本处理器（有自己的统一渲染），此文件只验证 shared 侧行为。
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel

from shared.common.exception_handler import register_exception_handlers


@pytest.fixture()
def client():
    app = FastAPI()
    register_exception_handlers(app)

    class Item(BaseModel):
        name: str
        count: int

    @app.get("/http-exc/{status}")
    async def http_exc(status: int):
        if status == 0:
            # 401 带 code 的 dict detail（auth.py 的抛法）
            raise HTTPException(status_code=401, detail={"code": 2003, "message": "账号不存在或已停用"})
        if status == 1:
            # 403 带 code 的 dict detail（internal_auth 的抛法，含 data）
            raise HTTPException(
                status_code=403,
                detail={"code": 3001, "message": "禁止访问", "data": None},
            )
        if status == 2:
            # dict detail 但缺 code → 走 status 映射分支
            raise HTTPException(status_code=404, detail={"msg": "无 code 键"})
        if status == 3:
            # detail=None
            raise HTTPException(status_code=500, detail=None)
        raise HTTPException(status_code=status, detail=f"错误-{status}")

    @app.post("/validate")
    async def validate(item: Item):
        return {"ok": item.name}

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_http_exception_dict_detail_with_code_rendered_as_is(client):
    """dict detail 含 code → 原样平铺 {code, message, data}，保住 2003 语义"""
    r = client.get("/http-exc/0")
    assert r.status_code == 401
    assert r.json() == {"code": 2003, "message": "账号不存在或已停用", "data": None}


def test_http_exception_dict_detail_with_code_and_data(client):
    """internal_auth 的 3001（detail 自带 data）→ 三键齐全"""
    r = client.get("/http-exc/1")
    assert r.status_code == 403
    assert r.json() == {"code": 3001, "message": "禁止访问", "data": None}


def test_http_exception_dict_detail_without_code_uses_status_mapping(client):
    """dict detail 缺 code → 按 status 映射，message 兜底「请求失败」"""
    r = client.get("/http-exc/2")
    assert r.status_code == 404
    assert r.json() == {"code": 4000, "message": "请求失败", "data": None}


def test_http_exception_none_detail(client):
    """detail=None 时 Starlette 会先把它换成状态短语（如 Internal Server Error），
    处理器按 str detail 渲染 —— 兜底「请求失败」分支仅防御性保留（detail 非 str 非 dict）"""
    r = client.get("/http-exc/3")
    assert r.status_code == 500
    assert r.json() == {"code": 5000, "message": "Internal Server Error", "data": None}


@pytest.mark.parametrize(
    "status,expected_code",
    [
        (400, 1000),
        (401, 2000),
        (403, 3000),
        (404, 4000),
        (405, 1000),
        (429, 5003),
        (500, 5000),
        (418, 5000),   # 未在映射表 → 兜底 5000
    ],
)
def test_http_exception_status_to_code_mapping(client, status, expected_code):
    r = client.get(f"/http-exc/{status}")
    assert r.status_code == status
    body = r.json()
    assert body["code"] == expected_code
    assert body["message"] == f"错误-{status}"
    assert body["data"] is None


def test_request_validation_error_unified_shape(client):
    """参数校验失败 → 422 + code 1000 + message 带首条 loc 路径"""
    r = client.post("/validate", json={"name": "x"})  # 缺 count
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 1000
    assert "参数校验失败" in body["message"]
    assert "count" in body["message"]
    assert body["data"] is None
