"""F1（2026-08-18）：四个检索后端结果透出 file_url → url 键。

背景：specialist 医学问答 citations.url 恒空——knowledge 四个检索后端（ES/DashVector
混合/百炼/本地 SQL）的结果 dict 都不含 url/file_url。修复后每个结果项须带非空 url，
映射自 KnowledgeDocument.file_url。本文件按既有打桩风格逐个后端断言。
"""
import pytest

from app.core.document_manager import DocumentManager
from app.db.repositories.knowledge_repo import KnowledgeRepository
from app.services.bailian_knowledge_client import BailianKnowledgeClient
from app.services.es_client import EsClient


# ---------- ES：搜索结果从 _source.file_url 映射 url ----------

def test_es_search_returns_url_from_source(monkeypatch):
    class _FakeES:
        def search(self, index, size, query):
            return {"hits": {"hits": [
                {"_source": {"title": "t", "content": "c", "doc_id": 7,
                             "file_url": "https://oss/x.pdf"}, "_score": 0.9},
            ]}}

    monkeypatch.setenv("ES_URL", "http://fake-es:9200")
    monkeypatch.setattr(EsClient, "client", lambda self: _FakeES())
    results = EsClient().search("q")
    assert results[0]["url"] == "https://oss/x.pdf"


# ---------- 本地 SQL：结果 dict 加 url=doc.file_url ----------

class _FakeLocalDoc:
    def __init__(self):
        self.id = 7
        self.title = "指南"
        self.content = "正文"
        self.evidence_level = "A"
        self.file_url = "https://oss/local.pdf"


class _FakeLocalQuery:
    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def all(self):
        return [_FakeLocalDoc()]


class _FakeLocalDb:
    def query(self, *a, **k):
        return _FakeLocalQuery()


def test_local_search_returns_url():
    results = KnowledgeRepository(_FakeLocalDb()).local_search("剂量", top_k=5)
    assert results[0]["url"] == "https://oss/local.pdf"


# ---------- DashVector 混合：融合结果透出 url ----------

class _FakeDVUrl:
    def query(self, vector, filter_expr=None, top_k=10):
        return [
            {"id": "doc_1_chunk_0", "score": 0.9, "doc_id": "1", "title": "文档一",
             "content": "向量正文", "chunk_index": 0, "url": "https://oss/a.pdf"},
        ]


class _FakeRepoUrl:
    def local_search(self, query, product_id=None, doc_type=None, top_k=10):
        return [
            {"title": "文档一", "content": "关键词正文", "evidence_level": "A",
             "score": 0.6, "doc_id": 1, "url": "https://oss/a.pdf"},
            {"title": "仅本地", "content": "本地独有", "evidence_level": "B",
             "score": 0.3, "doc_id": 3, "url": "https://oss/b.pdf"},
        ]


def test_hybrid_search_propagates_url(monkeypatch):
    monkeypatch.setattr("app.services.dashvector_client._embed", lambda text: [0.0])
    dm = DocumentManager.__new__(DocumentManager)
    dm.dashvector = _FakeDVUrl()
    dm.repo = _FakeRepoUrl()
    results = dm._hybrid_search("查询", product_id=1, doc_type="guideline", top_k=10)
    assert len(results) == 2
    assert results[0]["url"] == "https://oss/a.pdf"   # dashvector 优先
    assert results[1]["url"] == "https://oss/b.pdf"   # 仅 local


# ---------- 百炼：retrieve 结果从 metadata.original_file_url 映射 url ----------

def test_bailian_retrieve_maps_url():
    class _FakeNode:
        def __init__(self, metadata, text, score):
            self.metadata = metadata
            self.text = text
            self.score = score

    class _FakeData:
        nodes = [_FakeNode(
            {"file_name": "指南.pdf", "file_id": "file_1",
             "original_file_url": "https://oss/bailian.pdf"},
            "正文", 0.9,
        )]

    class _FakeBody:
        def __init__(self):
            self.data = _FakeData()
            self.success = True
            self.code = None

    class _FakeResponse:
        body = _FakeBody()

    class _FakeBailianClient:
        def retrieve(self, workspace_id, request):
            return _FakeResponse()

    bc = BailianKnowledgeClient.__new__(BailianKnowledgeClient)
    bc.client = _FakeBailianClient()
    bc.workspace_id = "ws"
    bc.index_id = "idx"
    results = bc.retrieve("剂量", top_k=5)
    assert results[0]["url"] == "https://oss/bailian.pdf"
    assert results[0]["doc_id"] == "file_1"
    assert results[0]["title"] == "指南.pdf"
