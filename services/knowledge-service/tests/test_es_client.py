"""EsClient 测试：不触发真实 elasticsearch 导入（client() 延迟 import，fake 替换）"""
from app.services.es_client import EsClient


class _FakeES:
    def search(self, index, size, query):
        return {"hits": {"hits": [{"_source": {"title": "t", "content": "c", "doc_id": 7}, "_score": 0.9}]}}


def test_search_returns_doc_id_from_source(monkeypatch):
    monkeypatch.setenv("ES_URL", "http://fake-es:9200")
    monkeypatch.setattr(EsClient, "client", lambda self: _FakeES())
    results = EsClient().search("q")
    assert len(results) == 1
    assert results[0]["doc_id"] == 7
    assert results[0]["title"] == "t"
    assert results[0]["content"] == "c"
    assert results[0]["score"] == 0.9


def test_is_configured_false_without_es_url(monkeypatch):
    monkeypatch.delenv("ES_URL", raising=False)
    assert EsClient().is_configured() is False
