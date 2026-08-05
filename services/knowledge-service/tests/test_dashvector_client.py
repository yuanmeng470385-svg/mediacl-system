"""DashVector 客户端（monkeypatch dashvector SDK）"""
import pytest

from app.services.dashvector_client import DashVectorClient, _embed
from app.services.document_processor import chunk_text


def test_is_configured(monkeypatch):
    monkeypatch.setenv("DASHVECTOR_API_KEY", "")
    monkeypatch.setenv("DASHVECTOR_ENDPOINT", "")
    assert DashVectorClient().is_configured() is False
    monkeypatch.setenv("DASHVECTOR_API_KEY", "k")
    monkeypatch.setenv("DASHVECTOR_ENDPOINT", "e")
    assert DashVectorClient().is_configured() is True


def test_chunk_text_sizes():
    text = "段落一。" * 300  # 900 字
    chunks = chunk_text(text, size=512)
    assert len(chunks) >= 2
    assert all(0 < len(c) <= 520 for c in chunks)


def test_embed(monkeypatch):
    class _FakeResp:
        status_code = 200
        output = {"embeddings": [{"embedding": [0.1] * 1536}]}

    monkeypatch.setattr("app.services.dashvector_client.dashscope.TextEmbedding.call", lambda **kw: _FakeResp())
    vec = _embed("测试文本")
    assert len(vec) == 1536


def test_upsert_and_query(monkeypatch):
    class _FakeCollection:
        def __init__(self):
            self.data = {}

        def upsert(self, docs):
            for d in docs:
                self.data[d.id] = d

        def query(self, vector, topk, filter=None, output_fields=None):  # noqa: A002
            return type("R", (), {"output": [
                type("D", (), {"id": "doc_1_chunk_0", "score": 0.9,
                                "fields": {"content": "文本", "doc_id": "1", "title": "t"}})
            ]})()

    class _FakeClient:
        def __init__(self, **kw):
            self.coll = _FakeCollection()

        def get(self, name):
            return self.coll

        def create(self, name, dimension, metric):
            raise Exception("already exists")  # 已存在则调用方兜底 get

    monkeypatch.setenv("DASHVECTOR_API_KEY", "k")
    monkeypatch.setenv("DASHVECTOR_ENDPOINT", "e")
    monkeypatch.setattr("dashvector.Client", _FakeClient)  # 实现用 dv.Client 运行期查找
    c = DashVectorClient()
    col = c._get_collection()
    from dashvector import Doc
    col.upsert([Doc(id="doc_1_chunk_0", vector=[0.1] * 1536, fields={"content": "文本", "doc_id": "1", "title": "t"})])
    out = c.query([0.1] * 1536, "doc_id = 1", top_k=1)
    assert out[0]["id"] == "doc_1_chunk_0"
