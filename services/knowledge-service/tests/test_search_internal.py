"""/search-internal 服务间检索端点：内部密钥鉴权 + 与 /search 同款校验/检索逻辑

- 无 X-Internal-Key → 403（require_internal_key 直连接口，网关 INTERNAL_PATHS 双重校验）
- 有 key → 200，返回结构含 results/source/empty
- 校验复用 validate_search_request：query 空 → ParamError；top_k 越界 → ParamError
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.api import knowledge as knowledge_api  # noqa: E402
from shared.common.db_session import get_db  # noqa: E402
from shared.common import internal_auth as internal_auth_module  # noqa: E402

TEST_KEY = "test-internal-key"


class _FakeSearchManager:
    """与 /search 测试同款打桩：DocumentManager.search 返回固定检索结果"""

    def __init__(self, db):
        pass

    def search(self, query, product_id=None, doc_type=None, top_k=10):
        return [
            {"doc_id": "1", "title": "文档一", "content": "正文", "score": 0.9,
             "backend": "local"},
        ], "local"


class _FakeDb:
    """search-internal 不落库，db 仅用于构造 manager；空实现即可"""

    pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(knowledge_api, "DocumentManager", _FakeSearchManager)
    # 让真实的 require_internal_key 走 test 密钥（不打 dependency override，
    # 直接验证 X-Internal-Key 头缺失/错误时 403、正确时放行）
    monkeypatch.setenv("INTERNAL_API_KEY", TEST_KEY)
    monkeypatch.setattr(internal_auth_module, "_INTERNAL_KEY", None)
    app.dependency_overrides[get_db] = lambda: _FakeDb()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _headers():
    return {"X-Internal-Key": TEST_KEY}


def test_search_internal_requires_internal_key(client):
    """无 X-Internal-Key → 403（code 3001），不能绕过内部密钥直连"""
    resp = client.post("/api/v1/knowledge/search-internal", json={"query": "剂量"})
    assert resp.status_code == 403
    assert resp.json()["code"] == 3001


def test_search_internal_with_key_returns_structure(client):
    """有 X-Internal-Key → 200，返回 data 含 results/source/empty"""
    resp = client.post("/api/v1/knowledge/search-internal",
                       headers=_headers(), json={"query": "剂量"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert "results" in data
    assert "source" in data
    assert "empty" in data
    assert data["source"] == "local"
    assert data["results"][0]["doc_id"] == "1"
    assert data["empty"] is False


def test_search_internal_empty_query_param_error(client):
    """query 空 → ParamError 400（复用 validate_search_request）"""
    resp = client.post("/api/v1/knowledge/search-internal",
                       headers=_headers(), json={"query": "  "})
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_search_internal_top_k_out_of_range_param_error(client):
    """top_k 越界（>50）→ ParamError 400（复用 validate_search_request）"""
    resp = client.post("/api/v1/knowledge/search-internal",
                       headers=_headers(), json={"query": "剂量", "top_k": 51})
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000
