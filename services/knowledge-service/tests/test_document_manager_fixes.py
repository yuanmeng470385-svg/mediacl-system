"""M22/M23/M27 修复单测：mock OSS/百炼/DashVector/ES 失败路径，不触碰真实外部依赖

覆盖：
- M22 版本上传顺序：OSS 失败不归档旧版；新文档入库成功后才归档旧版
- M23 审核流健壮性：approve 中途异常恢复可重试状态；reject 状态校验 + 索引清理
- M27 检索过滤：_filter_expr 单引号转义；百炼降级过滤丢弃告警；DashVector product_id 写 int
- M21 ES 接线：approve 成功后写入 ES；search 在 ES 配置时优先
"""
import logging

import pytest

from shared.common.response import BusinessError

from app.core.document_manager import DocumentManager
from app.services.bailian_knowledge_client import BailianKnowledgeError


# ---------- fakes ----------

class _Doc:
    def __init__(self, doc_id=5, status="draft", file_url=None, title="指南",
                 doc_type="guideline", product_id=7, revision=2, content=None):
        self.id = doc_id
        self.status = status
        self.file_url = file_url or "https://medagent-files.oss-cn-hangzhou.aliyuncs.com/knowledge/a.txt"
        self.title = title
        self.doc_type = doc_type
        self.product_id = product_id
        self.revision = revision
        self.content = content


class _FakeOSS:
    def __init__(self, upload_error=None, download_error=None):
        self.upload_error = upload_error
        self.download_error = download_error

    def upload_local_file(self, local_path):
        if self.upload_error:
            raise self.upload_error
        return "https://bucket/obj.pdf"

    def download_to_local(self, url, local_path):
        if self.download_error:
            raise self.download_error
        with open(local_path, "w", encoding="utf-8") as f:
            f.write("剂量 5mg，每日一次。")
        return local_path


class _FakeBailian:
    def __init__(self, error=None):
        self.error = error

    def import_document(self, local_path, original_file_url=None, tags=None):
        if self.error:
            raise self.error
        return {"file_id": "f1", "job_id": "j1"}

    def search(self, query, top_k=10, product_id=None, doc_type=None):
        return [{"doc_id": "f1", "title": "t", "content": "c", "score": 0.5}]


class _FakeDV:
    def __init__(self, configured=False):
        self.configured = configured
        self.upserted_fields = None
        self.deleted = []

    def is_configured(self):
        return self.configured

    def upsert_chunks(self, doc_id, title, chunks, fields=None):
        self.upserted_fields = fields
        return len(chunks)

    def delete_doc(self, doc_id):
        self.deleted.append(doc_id)
        return True


class _StatusRepo:
    """记录状态迁移 + 版本链操作的假 repo（无真实 DB）"""

    def __init__(self, doc, prev=None):
        self.doc = doc
        self._prev = prev
        self.status_log = []
        self.archived = []
        self.created = []

    def get(self, doc_id):
        return self.doc

    def try_mark_processing(self, doc_id, reviewer_id):
        """模拟原子抢占：仅 draft/rejected 可进入 processing（第二次调用返回 False）"""
        if self.doc is None or self.doc.status not in ("draft", "rejected"):
            return False
        self.status_log.append("processing")
        self.doc.status = "processing"
        return True

    def update_status(self, doc_id, status, reviewer_id=None):
        self.status_log.append(status)
        if self.doc is not None:
            self.doc.status = status
        return self.doc

    def find_latest_by_title(self, db, title, product_id=None):
        return self._prev

    def create_document(self, **kw):
        self.created.append(kw)
        return _Doc(doc_id=99, status="draft")

    def archive(self, db, doc):
        self.archived.append(doc)
        doc.status = "archived"


def _manager() -> DocumentManager:
    dm = DocumentManager.__new__(DocumentManager)
    dm.db = None  # fake repo 的 find_latest_by_title 忽略 db
    return dm


def _fake_es(monkeypatch, indexed=None, deleted=None):
    """配置 ES_URL + fake client；返回记录列表"""
    monkeypatch.setenv("ES_URL", "http://fake-es:9200")

    class _FakeES:
        def index(self, index, id, document):
            indexed.append((id, document))

        def delete(self, index, id, ignore=None):
            deleted.append(id)

    monkeypatch.setattr("app.services.es_client.EsClient.client", lambda self: _FakeES())


# ---------- M22: 版本上传顺序 ----------

def test_upload_oss_failure_keeps_old_version():
    prev = _Doc(doc_id=10, status="ready", revision=2)
    repo = _StatusRepo(prev, prev=prev)
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS(upload_error=RuntimeError("oss down"))

    with pytest.raises(RuntimeError):
        dm.create_from_upload(local_path="/tmp/x.pdf", title="指南", doc_type="guideline", uploader_id=1)

    assert repo.archived == []     # 旧版未被归档
    assert repo.created == []      # 未建新行
    assert prev.status == "ready"  # 旧版保持 ready


def test_upload_success_creates_new_then_archives_old():
    prev = _Doc(doc_id=10, status="ready", revision=2)
    repo = _StatusRepo(prev, prev=prev)
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS()

    doc = dm.create_from_upload(
        local_path="/tmp/x.pdf", title="指南", doc_type="guideline",
        uploader_id=1, product_id=7,
    )
    assert doc.status == "draft"
    assert repo.created[0]["revision"] == 3          # revision 链延续
    assert repo.created[0]["parent_doc_id"] == 10
    assert repo.created[0]["status"] == "draft"
    assert repo.archived == [prev]                   # 新文档入库成功后才归档旧版
    assert prev.status == "archived"


def test_upload_archive_failure_keeps_old_ready(caplog):
    prev = _Doc(doc_id=10, status="ready", revision=2)
    repo = _StatusRepo(prev, prev=prev)

    def _bad_archive(db, doc):
        raise RuntimeError("db down")

    repo.archive = _bad_archive
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS()

    doc = dm.create_from_upload(local_path="/tmp/x.pdf", title="指南", doc_type="guideline", uploader_id=1)
    assert doc.status == "draft"   # 新文档已入库
    assert prev.status == "ready"  # 旧版不受影响
    assert any("归档旧版文档" in r.message for r in caplog.records)


# ---------- M23: 审核流健壮性 ----------

def test_approve_oss_download_failure_restores_status():
    doc = _Doc()
    repo = _StatusRepo(doc)
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS(download_error=RuntimeError("oss dl failed"))
    dm.bailian = _FakeBailian()
    dm.dashvector = _FakeDV()

    with pytest.raises(BusinessError) as ei:
        dm.approve_document(5, reviewer_id=1)

    assert ei.value.code == 5000
    assert repo.status_log == ["processing", "draft"]  # 不卡死在 processing
    assert doc.status == "draft"


def test_approve_bailian_failure_restores_status():
    doc = _Doc()
    repo = _StatusRepo(doc)
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS()
    dm.bailian = _FakeBailian(error=BailianKnowledgeError("bailian down"))
    dm.dashvector = _FakeDV()

    with pytest.raises(BusinessError) as ei:
        dm.approve_document(5, reviewer_id=1)

    assert ei.value.code == 6000
    assert repo.status_log == ["processing", "draft"]
    assert doc.status == "draft"


def test_approve_rejected_doc_failure_restores_rejected():
    doc = _Doc(status="rejected")
    repo = _StatusRepo(doc)
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS(download_error=RuntimeError("down"))
    dm.bailian = _FakeBailian()
    dm.dashvector = _FakeDV()

    with pytest.raises(BusinessError):
        dm.approve_document(5, reviewer_id=1)

    assert doc.status == "rejected"  # 恢复到原状态而非卡 processing


def test_approve_success_indexes_es(monkeypatch):
    doc = _Doc()
    repo = _StatusRepo(doc)
    indexed = []
    _fake_es(monkeypatch, indexed=indexed, deleted=[])
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS()
    dm.bailian = _FakeBailian()
    dm.dashvector = _FakeDV()

    result = dm.approve_document(5, reviewer_id=1)

    assert result.status == "ready"
    assert repo.status_log == ["processing", "ready"]
    assert indexed and indexed[0][0] == "doc_5"
    assert indexed[0][1]["title"] == "指南"
    assert indexed[0][1]["product_id"] == 7
    assert indexed[0][1]["doc_type"] == "guideline"


def test_approve_success_es_failure_does_not_block(monkeypatch, caplog):
    doc = _Doc()
    repo = _StatusRepo(doc)
    monkeypatch.setenv("ES_URL", "http://fake-es:9200")

    class _BrokenES:
        def index(self, index, id, document):
            raise RuntimeError("es down")

    monkeypatch.setattr("app.services.es_client.EsClient.client", lambda self: _BrokenES())
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS()
    dm.bailian = _FakeBailian()
    dm.dashvector = _FakeDV()

    result = dm.approve_document(5, reviewer_id=1)
    assert result.status == "ready"  # ES 失败不阻塞审核
    assert any("ES 写入失败" in r.message for r in caplog.records)


def test_approve_without_bailian_writes_int_product_id(monkeypatch):
    doc = _Doc()
    repo = _StatusRepo(doc)
    dv = _FakeDV(configured=True)
    _fake_es(monkeypatch, indexed=[], deleted=[])
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS()
    dm.dashvector = dv

    result = dm.approve_without_bailian(5, reviewer_id=1)

    assert result.status == "ready"
    # M27: product_id 元数据统一 int（非 str），与 _filter_expr 的 int 字面量一致
    assert dv.upserted_fields == {"doc_type": "guideline", "product_id": 7}
    assert type(dv.upserted_fields["product_id"]) is int


def test_reject_ready_cleans_dashvector_and_es(monkeypatch, caplog):
    doc = _Doc(status="ready")
    repo = _StatusRepo(doc)
    dv = _FakeDV(configured=True)
    deleted = []
    _fake_es(monkeypatch, indexed=[], deleted=deleted)
    dm = _manager()
    dm.repo = repo
    dm.dashvector = dv

    result = dm.reject_document(5, reviewer_id=1)

    assert result.status == "rejected"
    assert dv.deleted == [5]          # DashVector 侧索引已删
    assert deleted == ["doc_5"]       # ES 侧索引已删
    # 百炼侧无删除能力：记 warning 说明（M23 注释的限制）
    assert any("百炼知识库文件无法经当前客户端删除" in r.message for r in caplog.records)


def test_reject_draft_does_not_touch_bailian(caplog):
    doc = _Doc(status="draft")
    repo = _StatusRepo(doc)
    dm = _manager()
    dm.repo = repo
    dm.dashvector = _FakeDV()

    with caplog.at_level(logging.WARNING):
        result = dm.reject_document(5, reviewer_id=1)

    assert result.status == "rejected"
    assert not any("百炼" in r.message for r in caplog.records)  # 未导入过百炼不告警


def test_reject_archived_raises():
    doc = _Doc(status="archived")
    repo = _StatusRepo(doc)
    dm = _manager()
    dm.repo = repo
    dm.dashvector = _FakeDV()

    with pytest.raises(BusinessError) as ei:
        dm.reject_document(5, reviewer_id=1)
    assert "不允许驳回" in ei.value.message
    assert dm.dashvector.deleted == []


# ---------- M27: 检索过滤 ----------

def test_filter_expr_escapes_single_quote():
    expr = DocumentManager._filter_expr(1, "guide'line")
    # DashVector filter 字符串字面量必须用双引号（单引号恒不命中），引号值被移除
    assert expr == 'product_id = 1 AND doc_type = "guideline"'
    assert DocumentManager._filter_expr(None, None) is None
    assert DocumentManager._filter_expr(0, "") is None
    assert DocumentManager._filter_expr(None, "guide'line") == 'doc_type = "guideline"'


def test_search_bailian_filter_drop_warns(caplog):
    dm = _manager()
    dm.dashvector = _FakeDV()
    dm.bailian = _FakeBailian()
    dm.repo = None  # 不会走到 local fallback

    with caplog.at_level(logging.WARNING):
        results, source = dm.search("q", product_id=3, doc_type="guideline", top_k=5)

    assert source == "bailian"
    assert any("过滤条件将被丢弃" in r.message for r in caplog.records)  # 不静默


def test_search_prefers_es_when_configured(monkeypatch):
    monkeypatch.setenv("ES_URL", "http://fake-es:9200")
    calls = []

    class _FakeES:
        def search(self, index, size, query):
            calls.append((index, size, query))
            return {"hits": {"hits": [
                {"_source": {"doc_id": 5, "title": "t", "content": "c"}, "_score": 0.9},
            ]}}

    monkeypatch.setattr("app.services.es_client.EsClient.client", lambda self: _FakeES())
    dm = _manager()

    results, source = dm.search("剂量", product_id=2, doc_type="guideline", top_k=5)

    assert source == "es"
    assert results[0]["doc_id"] == 5
    assert calls[0][1] == 5  # top_k
    assert calls[0][2]["bool"]["filter"] == [
        {"term": {"product_id": 2}},
        {"term": {"doc_type": "guideline"}},
    ]


def test_search_es_unconfigured_falls_back(monkeypatch):
    monkeypatch.delenv("ES_URL", raising=False)
    monkeypatch.setattr("app.services.dashvector_client._embed", lambda text: [0.0])
    dv = _FakeDV(configured=True)
    dv.query = lambda vector, filter_expr=None, top_k=10: [
        {"id": "doc_1_chunk_0", "score": 0.9, "doc_id": "1",
         "title": "t", "content": "c", "chunk_index": 0,
         "product_id": 7, "doc_type": "guideline"}
    ]
    dm = _manager()
    dm.dashvector = dv

    class _Local:
        def local_search(self, query, product_id=None, doc_type=None, top_k=10):
            return [{"doc_id": 1, "title": "t", "content": "c", "score": 0.8}]

    dm.repo = _Local()
    results, source = dm.search("q", top_k=5)
    assert source == "dashvector"
    assert results[0]["backend"] == "dashvector"


# ---------- 2026-08-11: 并发防抖（原子抢占，防双击/多管理同时审核） ----------

def test_approve_concurrent_double_click_second_fails():
    """并发防抖：状态已进入 processing 后，第二个请求原子抢占失败 → 400"""
    doc = _Doc()
    repo = _StatusRepo(doc)
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS()
    dm.bailian = _FakeBailian()
    dm.dashvector = _FakeDV()

    # 模拟并发场景：另一请求已把状态置为 processing（抢占逻辑同：draft→processing）
    assert repo.try_mark_processing(5, reviewer_id=1) is True
    assert doc.status == "processing"

    with pytest.raises(BusinessError) as ei:
        dm.approve_document(5, reviewer_id=2)

    assert ei.value.code == 4001
    # 第二请求重读到 processing：命中预检查「当前状态 processing 不允许审核」（4001）
    assert "不允许审核" in str(ei.value)
    # 第二个请求不得触发任何状态变更（status_log 只有第一个请求的 processing）
    assert repo.status_log == ["processing"]


def test_approve_concurrent_race_both_read_draft():
    """竞态窗口：两个请求都读到 draft，原子抢占只放行一个"""
    doc = _Doc()

    class _RacingRepo(_StatusRepo):
        """抢占返回 False 模拟并发窗口内另一请求已抢走"""

        def try_mark_processing(self, doc_id, reviewer_id):
            if self.doc.status not in ("draft", "rejected"):
                return False
            # 模拟另一个请求抢先：状态已变 processing
            self.doc.status = "processing"
            return False

    repo = _RacingRepo(doc)
    dm = _manager()
    dm.repo = repo
    dm.oss = _FakeOSS()
    dm.bailian = _FakeBailian()
    dm.dashvector = _FakeDV()

    with pytest.raises(BusinessError) as ei:
        dm.approve_document(5, reviewer_id=1)

    assert ei.value.code == 4001
    assert doc.status == "processing"  # 不被第二请求改动
