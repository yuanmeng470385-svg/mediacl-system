"""LLM 实时推荐测试（假 Qwen，不连真实服务）"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest
import asyncio

import app.core.visit_manager as vm_module
from app.models.visit_record import VisitRecord

# 复用 test_visit_manager.py 的 FakeDb（同目录 import）
from test_visit_manager import FakeDb


class FakeQwen:
    """假 QwenClient：可注入返回内容或抛异常"""
    def __init__(self, content=None, error=None, call_count=None):
        self._content = content
        self._error = error
        self.calls = [] if call_count is None else call_count

    def chat(self, messages, model=None, temperature=0.1, max_tokens=2000):
        self.calls.append(messages)
        if self._error:
            raise self._error
        return {"content": self._content, "usage": {}}


class FakeAudit:
    """假 write_audit_log：记录调用参数，不连真实审计服务（真实版会异步打网关）"""
    def __init__(self):
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return None


def make_manager(fake_qwen):
    return vm_module.VisitManager(qwen=fake_qwen)


def make_record():
    rec = VisitRecord()
    rec.id = 1
    rec.visit_time = datetime.now()
    return rec


def test_short_sentence_not_triggered():
    q = FakeQwen(content='{"key_nodes":[]}')
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "好的"))
    assert result is None
    assert q.calls == []  # 短句不触发


def test_throttled_within_cooldown():
    q = FakeQwen(content='{"key_nodes":[]}')
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    rec.key_nodes = [{"type": "interest_point", "label": "认可", "quote": "x",
                      "created_at": datetime.now().isoformat()}]  # 刚标记过 → 冷却中
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None
    assert q.calls == []


def test_llm_failure_degrades():
    q = FakeQwen(error=RuntimeError("LLM 挂了"))
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None  # 降级：返回 None 而非抛异常


def test_success_returns_and_persists(monkeypatch):
    content = ('{"key_nodes":[{"type":"decision_point","label":"决策表态",'
               '"quote":"主任表示考虑使用"}],"suggestion":{"topic":"价格",'
               '"advice":"建议强调药物经济学优势"}}')
    q = FakeQwen(content=content)
    m = make_manager(q)
    audit = FakeAudit()
    monkeypatch.setattr(vm_module, "write_audit_log", audit)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "主任表示考虑使用我们的产品"))
    assert result is not None
    assert result["key_nodes"][0]["type"] == "decision_point"
    assert result["ai_suggestion"]["advice"] == "建议强调药物经济学优势"
    assert len(rec.key_nodes) == 1  # 已落库
    assert rec.key_nodes[0]["created_at"]
    # 审计打桩断言：真实 write_audit_log 会异步 POST 网关，这里验证推荐审计确实发出
    assert len(audit.calls) == 1
    assert audit.calls[0]["action"] == "visit_llm_recommend"
    assert audit.calls[0]["ai_involved"] is True


def test_unparseable_output_degrades():
    q = FakeQwen(content="抱歉我无法处理")
    m = make_manager(q)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None


def test_process_transcript_includes_recommendation(monkeypatch):
    """集成：process_transcript 响应含 key_nodes/ai_suggestion"""
    q = FakeQwen(content='{"key_nodes":[{"type":"interest_point","label":"认可","quote":"q"}],"suggestion":null}')
    m = make_manager(q)

    async def _fake_check_compliance(text, ctx):
        return {"blocked": False, "violations": []}

    audit = FakeAudit()
    monkeypatch.setattr(vm_module, "write_audit_log", audit)
    monkeypatch.setattr(vm_module, "check_compliance", _fake_check_compliance)
    db = FakeDb()
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m.process_transcript(db, rec.id, 1, text_content="这句话超过六个字了"))
    assert "key_nodes" in result
    assert result["key_nodes"][0]["type"] == "interest_point"
    assert "ai_suggestion" in result
    # process_transcript 有两次审计（visit_transcript + visit_llm_recommend），均已打桩
    actions = [c["action"] for c in audit.calls]
    assert "visit_transcript" in actions
    assert "visit_llm_recommend" in actions


# ---------- F2 回归（2026-08-13）：行锁不跨 LLM 调用、冷却判断无锁 ----------

class LockTrackingFakeQwen(FakeQwen):
    """记录 chat 调用顺序的假 Qwen（与锁事件列表共同断言 LLM 在锁外）"""
    def __init__(self, content=None, events=None):
        super().__init__(content=content)
        self._events = events

    def chat(self, messages, model=None, temperature=0.1, max_tokens=2000):
        if self._events is not None:
            self._events.append("chat")
        return super().chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)


class LockTrackingDb(FakeDb):
    """记录 with_for_update（行锁）调用事件的假 session"""
    def __init__(self, events):
        super().__init__()
        self._events = events

    def query(self, model_cls):
        q = super().query(model_cls)

        def tracked_for_update():
            self._events.append("lock")
            return q
        q.with_for_update = tracked_for_update
        return q


def test_f2_cooldown_check_is_lock_free():
    """F2：冷却命中 → 既不调 LLM 也不加任何行锁（旧实现先 FOR UPDATE 再判冷却）"""
    events = []
    q = LockTrackingFakeQwen(content='{"key_nodes":[]}', events=events)
    m = make_manager(q)
    db = LockTrackingDb(events)
    rec = make_record()
    rec.key_nodes = [{"type": "interest_point", "label": "认可", "quote": "x",
                      "created_at": datetime.now().isoformat()}]  # 刚标记过 → 冷却中
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None
    assert q.calls == []
    assert events == [], f"冷却命中不应加行锁: {events}"


def test_f2_llm_call_runs_outside_row_lock(monkeypatch):
    """F2：成功路径 LLM 调用在锁外 —— 事件顺序 chat → lock（锁只覆盖追加窗口）"""
    events = []
    content = ('{"key_nodes":[{"type":"decision_point","label":"决策表态",'
               '"quote":"主任表示考虑使用"}],"suggestion":null}')
    q = LockTrackingFakeQwen(content=content, events=events)
    m = make_manager(q)
    audit = FakeAudit()
    monkeypatch.setattr(vm_module, "write_audit_log", audit)
    db = LockTrackingDb(events)
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "主任表示考虑使用我们的产品"))
    assert result is not None
    assert events == ["chat", "lock"], f"LLM 调用应在锁外（chat 先于 lock）: {events}"
    assert len(rec.key_nodes) == 1


def test_f2_llm_parse_failure_never_takes_lock(monkeypatch):
    """F2：解析失败路径（旧实现 return 不 commit 锁持有到 session 关闭）→ 不加锁"""
    events = []
    q = LockTrackingFakeQwen(content="抱歉我无法处理", events=events)
    m = make_manager(q)
    db = LockTrackingDb(events)
    rec = make_record()
    db.add(rec)
    result = asyncio.run(m._llm_recommend(db, rec.id, 1, "这句话超过六个字了"))
    assert result is None
    assert events == ["chat"], f"解析失败不应加行锁: {events}"


def test_f2_lock_window_rereads_row_preserves_concurrent_appends(monkeypatch):
    """F2：锁内重读该行再追加 —— LLM 调用期间另一请求已追加的节点不覆盖丢失"""
    content = ('{"key_nodes":[{"type":"interest_point","label":"认可","quote":"q"}],"suggestion":null}')
    q = FakeQwen(content=content)
    m = make_manager(q)
    audit = FakeAudit()
    monkeypatch.setattr(vm_module, "write_audit_log", audit)

    rec_read = make_record()    # 无锁读看到的旧行（无 key_nodes）
    rec_locked = make_record()  # 锁内重读看到的新行（已有并发追加）
    rec_locked.key_nodes = [{"type": "decision_point", "label": "并发追加", "quote": "c",
                             "created_at": datetime.now().isoformat()}]

    def fake_get(db, visit_id, for_update=False):
        return rec_locked if for_update else rec_read
    monkeypatch.setattr(vm_module.VisitRepo, "get", staticmethod(fake_get))

    db = FakeDb()
    result = asyncio.run(m._llm_recommend(db, rec_read.id, 1, "这句话超过六个字了"))
    assert result is not None
    assert len(rec_locked.key_nodes) == 2, "追加应基于锁内重读的新行，并发节点不能丢"
    assert rec_locked.key_nodes[0]["label"] == "并发追加"
    assert rec_locked.key_nodes[1]["label"] == "认可"


def test_f2_lock_window_reread_populates_existing_real_sessions():
    """F2 终审（2026-08-13）：真实 SQLAlchemy 会话验证锁内重读刷新为最新已提交行

    上面的 monkeypatch 用例用替换对象模拟重读，不验证真实 ORM 语义。本用例用
    SQLite 内存库（StaticPool，与 auth-service/tests/test_auth.py 同模式）+
    两个独立 Session：A 无锁读缓存实例 → B 修改 key_nodes 并 commit → A 锁内
    再次 repo.get(for_update=True) → 必须读到 B 的新值（VisitRepo.get 的
    populate_existing 生效，identity map 原地刷新而非返回旧属性值）。
    """
    from sqlalchemy import BigInteger, create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from shared.models.base import Base
    from app.db.repositories.visit_repo import VisitRepo

    # SQLite 编译垫片（同 test_auth.py 模式，仅影响 SQLite 编译路径，PG 不受影响）：
    # BigInteger 编译为 INTEGER 才能自增；JSONB SQLite 渲染不了 → JSON
    # （bind/result 处理器仍是 JSON 序列化，key_nodes 列表往返无损）
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
    Base.metadata.create_all(engine, tables=[VisitRecord.__table__])
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db_a = db_b = None
    try:
        # 会话 A：建行 + 无锁读缓存实例（对应 _llm_recommend 冷却判断前的读）
        db_a = Session()
        rec = VisitRecord(visit_time=datetime.now())
        db_a.add(rec)
        db_a.commit()
        visit_id = rec.id
        cached = VisitRepo.get(db_a, visit_id)
        assert cached.key_nodes is None

        # 会话 B：并发修改 key_nodes 并 commit（对应 LLM 调用窗口内的并发追加）
        db_b = Session()
        other = VisitRepo.get(db_b, visit_id)
        other.key_nodes = [{
            "type": "decision_point", "label": "并发追加", "quote": "c",
            "created_at": datetime.now().isoformat(),
        }]
        db_b.commit()

        # 会话 A：锁内重读 —— 必须读到 B 已提交的新行
        reread = VisitRepo.get(db_a, visit_id, for_update=True)
        assert reread is cached, "identity map 应返回同一实例（populate_existing 原地刷新）"
        assert reread.key_nodes is not None
        assert len(reread.key_nodes) == 1, "锁内重读应刷新为 B 会话已提交的新 key_nodes"
        assert reread.key_nodes[0]["label"] == "并发追加"
    finally:
        if db_a is not None:
            db_a.close()
        if db_b is not None:
            db_b.close()
        engine.dispose()
