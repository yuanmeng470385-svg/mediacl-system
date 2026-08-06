"""拜访管理器集成测试 — 完整拜访流程（假外部依赖，不连真实服务）

覆盖：准备包降级 / 开始拜访 / 转写+违规检测 / 结束生成记录 / 跟进建议
"""
import os
import sys
import asyncio
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import app.core.visit_manager as vm_module
import app.services.specialist_client as spec_client
import app.services.compliance_client as comp_client
import app.services.audit_client as aud_client
from app.models.visit_record import VisitRecord

# ---------- fakes ----------

class FakeDb:
    """假 session：模拟 SQLAlchemy Session 的核心接口（add/commit/refresh/query/execute）"""
    _records = {}  # class-level: id -> VisitRecord

    def __init__(self):
        self._id_counter = 1
        FakeDb._records.clear()

    def add(self, obj):
        obj.id = self._id_counter
        self._id_counter += 1
        FakeDb._records[obj.id] = obj

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def query(self, model_cls):
        return _FakeQuery(model_cls)

    def execute(self, stmt, params=None, **kw):
        return _FakeResult(FakeDb, stmt, params)


class _FakeQuery:
    """模拟 SQLAlchemy Query（仅支持 .filter().first()）"""

    def __init__(self, model_cls):
        self._model = model_cls
        self._filters = []

    def filter(self, condition):
        self._filters.append(condition)
        return self

    def first(self):
        for rec in FakeDb._records.values():
            if self._match(rec):
                return rec
        return None

    def order_by(self, *_):
        return self

    def offset(self, n):
        return self

    def limit(self, n):
        return self

    def all(self):
        return [r for r in FakeDb._records.values() if self._match(r)]

    def count(self):
        return len(self.all())

    def _match(self, rec):
        # 简易匹配：只检查 VisitRecord.id == N 和 is_(None)/isnot(None)
        for cond in self._filters:
            if hasattr(cond, "left") and hasattr(cond, "right"):
                left_val = getattr(rec, cond.left.key, None)
                right_val = cond.right.value if hasattr(cond.right, "value") else cond.right
                if hasattr(cond, "operator"):
                    opname = cond.operator.__name__ if hasattr(cond.operator, "__name__") else str(cond.operator)
                    if "is_" in opname or opname == "is_":
                        left_val = getattr(rec, cond.left.key, None) if hasattr(cond.left, "key") else None
        return True


class _FakeResult:
    """模拟 SQLAlchemy Result — 直读 SQL 查询"""

    def __init__(self, db, stmt, params):
        self._stmt = str(stmt)
        self._params = params or {}

    def mappings(self):
        class _Mappings:
            def __init__(self, rows):
                self._rows = rows

            def first(self):
                return self._rows[0] if self._rows else None

            def all(self):
                return self._rows

        s = self._stmt.lower()
        pid = self._params.get("hcp_id")

        if "hcps" in s:
            # 只对 hcp_id=1 返回数据，模拟"不存在"场景
            rows = [{
                "id": 1, "name": "张伟", "hospital": "协和医院",
                "department": "肿瘤内科", "title": "主任医师",
                "specialty": "肿瘤学", "region": "北京", "tags": ["KOL"],
            }] if pid == 1 else []
        elif "digital_specialists" in s:
            rows = [{"id": 10, "name": "肿瘤专员-小K"}]
        elif "visit_records" in s:
            rows = [r.to_dict() for r in FakeDb._records.values()
                    if r.hcp_id == pid][:3]
        else:
            rows = []
        return _Mappings(rows)


class FakeTingwu:
    """听悟 Mock"""
    def transcribe(self, audio_url):
        return {
            "text": "张医生：这个药价格有点贵\n代表：是的，但是医保可以报销70%",
            "speakers": ["speaker_0", "speaker_1"],
        }


# ---------- fake async clients ----------

async def _fake_specialist_ok(specialist_id, question, user_id, session_id=None, auth_token=None):
    return {"answer": json.dumps({
        "summary": "本次拜访讨论了产品疗效和价格问题，医生持中性态度",
        "key_points": ["价格讨论", "疗效认可"],
        "hcp_interests": ["长期安全性", "医保政策"],
        "hcp_objections": ["担心副作用"],
        "follow_up_suggestions": ["发送III期文献", "预约下周电话随访"],
        "sentiment": "neutral",
        "next_visit_plan": {"recommended_time": "2026-08-10",
                            "recommended_topics": ["安全性数据"],
                            "materials_to_send": ["文献包"]}
    }), "blocked": False, "session_id": "test-session"}


async def _fake_specialist_fail(specialist_id, question, user_id, session_id=None, auth_token=None):
    """AI 不可用 → 降级"""
    return {"answer": "", "blocked": False, "degraded": True, "error": "AI 服务不可用"}


async def _fake_specialist_previsit(specialist_id, question, user_id, session_id=None, auth_token=None):
    """pre-visit：按固定 schema 输出推荐内容"""
    return {"answer": json.dumps({
        "suggested_topics": ["指南更新", "适应症扩展", "医保政策"],
        "red_lines": ["不得夸大疗效"],
        "opening_remarks": "张主任您好，今天想和您交流最新的临床数据",
        "materials": ["III期研究摘要", "医保政策文件"],
        "last_follow_up": "发送安全性长期随访数据",
    }), "blocked": False, "session_id": "test-session"}


async def _fake_compliance_ok(content, context=None):
    return {"blocked": False, "violations": [], "risk_level": "none"}


async def _fake_compliance_blocked(content, context=None):
    return {"blocked": True, "violations": [{"rule": "R001", "reason": "test"}], "risk_level": "high"}


async def _fake_audit_ok(**kwargs):
    return 1


# ---------- patches ----------
# visit_manager.py 在模块级别 import 了这些函数，形成了本地引用，
# 必须 patch vm_module 而非原始服务模块

ORIG_CHAT = vm_module.chat_with_specialist
ORIG_COMP = vm_module.check_compliance
ORIG_AUDIT = vm_module.write_audit_log


def setup_module():
    vm_module.chat_with_specialist = _fake_specialist_ok
    vm_module.check_compliance = _fake_compliance_ok
    vm_module.write_audit_log = _fake_audit_ok


def teardown_module():
    vm_module.chat_with_specialist = ORIG_CHAT
    vm_module.check_compliance = ORIG_COMP
    vm_module.write_audit_log = ORIG_AUDIT


# ---------- tests ----------

def test_prepare_visit_no_hcp():
    """医生不存在 → BusinessError"""
    from app.core.visit_manager import VisitManager
    mgr = VisitManager(tingwu=FakeTingwu())
    db = FakeDb()
    try:
        asyncio.run(mgr.prepare_visit(db, hcp_id=999, user_id=1, product_id=1))
        assert False, "应抛 BusinessError"
    except Exception as e:
        assert "不存在" in str(e)


def test_start_visit():
    """开始拜访 → 创建记录，返回 id + visit_id 别名 + status=in_progress"""
    from app.core.visit_manager import VisitManager
    mgr = VisitManager(tingwu=FakeTingwu())
    db = FakeDb()
    result = asyncio.run(mgr.start_visit(db, hcp_id=1, user_id=1, product_id=1))
    assert "id" in result
    assert result["visit_id"] == result["id"]  # 移动端契约：读取 visit_id
    assert result["status"] == "in_progress"


def test_process_transcript_with_text():
    """直接文本传入 → 转写+合规检查+异议识别"""
    from app.core.visit_manager import VisitManager
    db = FakeDb()
    mgr = VisitManager(tingwu=FakeTingwu())
    start = asyncio.run(mgr.start_visit(db, hcp_id=1, user_id=1, product_id=1))
    visit_id = start["id"]

    result = asyncio.run(mgr.process_transcript(
        db, visit_id, user_id=1, text_content="这个药价格有点贵啊"
    ))
    assert result["visit_id"] == visit_id
    assert result["transcript"] == "这个药价格有点贵啊"
    assert "compliance" in result
    assert "objections" in result
    types = [o["type"] for o in result["objections"].get("objections", [])]
    assert "price" in types


def test_end_visit_generates_record():
    """结束拜访 → AI 生成结构化记录并入库"""
    from app.core.visit_manager import VisitManager
    db = FakeDb()
    mgr = VisitManager(tingwu=FakeTingwu())
    start = asyncio.run(mgr.start_visit(db, hcp_id=1, user_id=1, product_id=1))
    visit_id = start["id"]
    asyncio.run(mgr.process_transcript(db, visit_id, user_id=1, text_content="聊了疗效和价格"))
    result = asyncio.run(mgr.end_visit(db, visit_id, user_id=1))
    assert result["status"] == "completed"
    assert result["visit_id"] == visit_id  # 移动端契约：读取 visit_id
    assert result["ai_summary"]
    assert "本次拜访" in result["ai_summary"]
    assert result["sentiment"] == "neutral"


def test_end_visit_blocked_summary():
    """合规拦截 AI 总结 → 使用模板话术替换"""
    from app.core.visit_manager import VisitManager
    vm_module.check_compliance = _fake_compliance_blocked

    db = FakeDb()
    mgr = VisitManager(tingwu=FakeTingwu())
    start = asyncio.run(mgr.start_visit(db, hcp_id=1, user_id=1, product_id=1))
    visit_id = start["id"]
    asyncio.run(mgr.process_transcript(db, visit_id, user_id=1, text_content="test"))
    result = asyncio.run(mgr.end_visit(db, visit_id, user_id=1))
    assert "拦截" in result["ai_summary"]

    vm_module.check_compliance = ORIG_COMP  # 恢复


def test_follow_up():
    """跟进建议生成"""
    from app.core.visit_manager import VisitManager
    db = FakeDb()
    mgr = VisitManager(tingwu=FakeTingwu())
    start = asyncio.run(mgr.start_visit(db, hcp_id=1, user_id=1, product_id=1))
    visit_id = start["id"]
    asyncio.run(mgr.process_transcript(db, visit_id, user_id=1, text_content="test"))
    asyncio.run(mgr.end_visit(db, visit_id, user_id=1))
    result = asyncio.run(mgr.follow_up(db, visit_id, user_id=1))
    assert result["visit_id"] == visit_id
    assert "follow_up" in result


# ---------- 修复 3：pre-visit 推荐内容 schema 化 ----------

def test_parse_recommendations_plain_json():
    """英文键 JSON 直接解析"""
    from app.core.visit_manager import _parse_recommendations
    raw = json.dumps({
        "suggested_topics": ["指南更新", "适应症扩展", "医保政策"],
        "red_lines": ["不得承诺疗效"],
        "opening_remarks": "张主任您好",
        "materials": ["III期文献"],
        "last_follow_up": "发送安全性数据",
    })
    r = _parse_recommendations(raw)
    assert r["suggested_topics"] == ["指南更新", "适应症扩展", "医保政策"]
    assert r["red_lines"] == ["不得承诺疗效"]
    assert r["opening_remarks"] == "张主任您好"
    assert r["materials"] == ["III期文献"]
    assert r["last_follow_up"] == "发送安全性数据"


def test_parse_recommendations_markdown_fence():
    """剥离 markdown 代码围栏"""
    from app.core.visit_manager import _parse_recommendations
    raw = '```json\n{"suggested_topics": ["话题A", "话题B", "话题C"], "red_lines": [], "opening_remarks": "开场", "materials": [], "last_follow_up": ""}\n```'
    r = _parse_recommendations(raw)
    assert r["suggested_topics"] == ["话题A", "话题B", "话题C"]
    assert r["opening_remarks"] == "开场"


def test_parse_recommendations_chinese_keys():
    """中文键归一化为固定 schema 英文键"""
    from app.core.visit_manager import _parse_recommendations
    raw = json.dumps({
        "推荐话题": ["话题A", "话题B"],
        "红线提醒": ["红线1"],
        "开场白建议": "您好张医生",
        "材料": ["文献包"],
        "上次未完成的跟进项": "发资料",
    })
    r = _parse_recommendations(raw)
    assert r["suggested_topics"] == ["话题A", "话题B"]
    assert r["red_lines"] == ["红线1"]
    assert r["opening_remarks"] == "您好张医生"
    assert r["materials"] == ["文献包"]
    assert r["last_follow_up"] == "发资料"


def test_parse_recommendations_invalid_returns_empty_structure():
    """解析失败 / 形状不对 → 返回空结构，不泄漏原始文本"""
    from app.core.visit_manager import _parse_recommendations
    empty = {"suggested_topics": [], "red_lines": [], "opening_remarks": "", "materials": [], "last_follow_up": ""}
    bad_inputs = [
        "",
        None,
        "这不是JSON",
        "```json\n{broken\n```",
        "[1, 2, 3]",
        '{"suggested_topics": "字符串不是列表"}',
        '{"推荐话题": 123}',
    ]
    for bad in bad_inputs:
        assert _parse_recommendations(bad) == empty, f"输入 {bad!r} 应返回空结构"


def test_prepare_visit_returns_structured_recommendations():
    """pre-visit AI 输出按固定 schema 解析返回"""
    from app.core.visit_manager import VisitManager
    vm_module.chat_with_specialist = _fake_specialist_previsit
    try:
        db = FakeDb()
        mgr = VisitManager(tingwu=FakeTingwu())
        result = asyncio.run(mgr.prepare_visit(db, hcp_id=1, user_id=1, product_id=1))
        recs = result["recommendations"]
        assert recs["suggested_topics"] == ["指南更新", "适应症扩展", "医保政策"]
        assert recs["red_lines"] == ["不得夸大疗效"]
        assert recs["opening_remarks"].startswith("张主任")
        assert "content" not in recs  # 不再回退为原始文本
    finally:
        vm_module.chat_with_specialist = _fake_specialist_ok


def test_prepare_visit_ai_garbage_returns_empty_structure():
    """AI 输出不可解析 → 返回空结构而非原始文本"""
    from app.core.visit_manager import VisitManager

    async def _fake_specialist_garbage(specialist_id, question, user_id, session_id=None, auth_token=None):
        return {"answer": "随便一段话", "blocked": False, "degraded": False, "session_id": "s"}

    vm_module.chat_with_specialist = _fake_specialist_garbage
    try:
        db = FakeDb()
        mgr = VisitManager(tingwu=FakeTingwu())
        result = asyncio.run(mgr.prepare_visit(db, hcp_id=1, user_id=1, product_id=1))
        assert result["recommendations"] == {
            "suggested_topics": [], "red_lines": [], "opening_remarks": "", "materials": [], "last_follow_up": "",
        }
        assert "随便一段话" not in json.dumps(result["recommendations"], ensure_ascii=False)
    finally:
        vm_module.chat_with_specialist = _fake_specialist_ok


# ---------- 修复 4：end_visit AI 降级不锁死，可重试 ----------

def test_end_visit_ai_failure_writes_placeholder_then_retry():
    """AI 失败写占位串 → 不算已结束，可再次 end 重试，成功后覆盖占位串"""
    from app.core.visit_manager import VisitManager, AI_SUMMARY_PLACEHOLDER
    db = FakeDb()
    mgr = VisitManager(tingwu=FakeTingwu())
    start = asyncio.run(mgr.start_visit(db, hcp_id=1, user_id=1, product_id=1))
    visit_id = start["id"]
    asyncio.run(mgr.process_transcript(db, visit_id, user_id=1, text_content="聊了疗效和价格"))

    vm_module.chat_with_specialist = _fake_specialist_fail
    try:
        result = asyncio.run(mgr.end_visit(db, visit_id, user_id=1))
        assert result["ai_summary"] == AI_SUMMARY_PLACEHOLDER
        # 占位串不算已结束 → 再次 end 不抛"已结束"，允许重试
        result2 = asyncio.run(mgr.end_visit(db, visit_id, user_id=1))
        assert result2["ai_summary"] == AI_SUMMARY_PLACEHOLDER

        # AI 恢复后重试成功 → 占位串被真实总结覆盖
        vm_module.chat_with_specialist = _fake_specialist_ok
        result3 = asyncio.run(mgr.end_visit(db, visit_id, user_id=1))
        assert result3["ai_summary"] != AI_SUMMARY_PLACEHOLDER
        assert "本次拜访" in result3["ai_summary"]
    finally:
        vm_module.chat_with_specialist = _fake_specialist_ok


def test_end_visit_no_duplicate_after_success():
    """成功结束后再次 end → 抛业务错误（不可重复覆盖）"""
    from app.core.visit_manager import VisitManager
    db = FakeDb()
    mgr = VisitManager(tingwu=FakeTingwu())
    start = asyncio.run(mgr.start_visit(db, hcp_id=1, user_id=1, product_id=1))
    visit_id = start["id"]
    asyncio.run(mgr.end_visit(db, visit_id, user_id=1))
    try:
        asyncio.run(mgr.end_visit(db, visit_id, user_id=1))
        assert False, "应抛 BusinessError"
    except Exception as e:
        assert "已结束" in str(e)
