"""_hybrid_search 融合测试：dashvector doc_id(str) 与 local doc_id(int) 类型统一"""
import pytest

from app.core.document_manager import DocumentManager


class _FakeDashVector:
    """fake dashvector.query：doc_id 为字符串"""

    def query(self, vector, filter_expr, top_k=10):
        return [
            {"id": "doc_1_chunk_0", "score": 0.9, "doc_id": "1",
             "title": "文档一", "content": "向量正文", "chunk_index": 0,
             "product_id": "1", "doc_type": "guideline"},
            {"id": "doc_2_chunk_0", "score": 0.5, "doc_id": "2",
             "title": "文档二", "content": "向量正文二", "chunk_index": 0,
             "product_id": "1", "doc_type": "guideline"},
        ]


class _FakeRepo:
    """fake repo.local_search：doc_id 为 int，含与向量同文档 + 一条仅 local"""

    def local_search(self, query, product_id=None, doc_type=None, top_k=10):
        return [
            {"title": "文档一", "content": "关键词正文", "evidence_level": "A",
             "score": 0.6, "doc_id": 1},
            {"title": "仅本地", "content": "本地独有", "evidence_level": "B",
             "score": 0.3, "doc_id": 3},
        ]


def test_hybrid_search_merges_str_and_int_doc_ids(monkeypatch):
    monkeypatch.setattr("app.services.dashvector_client._embed", lambda text: [0.0])
    dm = DocumentManager.__new__(DocumentManager)
    dm.dashvector = _FakeDashVector()
    dm.repo = _FakeRepo()
    results = dm._hybrid_search("查询", product_id=1, doc_type="guideline", top_k=10)

    # 同文档（dashvector "1" / local 1）合并为一条，共 3 条
    assert len(results) == 3
    # 排序按 score 降序
    assert [r["doc_id"] for r in results] == ["1", "2", 3]
    # 合并条目保留 dashvector 优先写入的 doc_id（str）与 backend
    assert results[0]["doc_id"] == "1"
    assert results[0]["backend"] == "dashvector"
    # 仅 local 的文档 doc_id 保持 int
    assert results[2]["doc_id"] == 3
    assert results[2]["backend"] == "local"
    # 加权分 = 0.7 * v / vec_max + 0.3 * k / kw_max（vec_max=0.9, kw_max=0.6）
    assert results[0]["score"] == pytest.approx(0.7 * 0.9 / 0.9 + 0.3 * 0.6 / 0.6)
    assert results[1]["score"] == pytest.approx(0.7 * 0.5 / 0.9)
    assert results[2]["score"] == pytest.approx(0.3 * 0.3 / 0.6)
