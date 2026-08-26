"""题库端点测试（Task 3 题库 CRUD + 审核；Task 5 追加考试判分用例）"""
import os
import sys

import jwt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")
os.environ["AUTH_DEV_MODE"] = "true"

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.common.auth import create_token
from shared.common.db_session import get_db
from shared.models.base import Base
from shared.models.training_exam import ExamQuestion, ExamRecord, TrainingMaterial
from shared.models.user import User

import app.api.exams as exams_api
from app.main import app


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


# ExamQuestion.options/answer 是 JSONB，SQLite 渲染不了（SQLAlchemy 2.0 无 JSONB 兜底），
# 参照 specialist-service 测试模式加编译垫片（JSONB → JSON）。
@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    return "JSON"


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def _token(user_id: int, role: str) -> dict:
    token = create_token(user_id=user_id, username=f"u{user_id}", role=role)
    return {"Authorization": f"Bearer {token}"}


# H-1（2026-08-24 审查修复）：直接用被测模块签发考试会话，避免依赖 /start 的随机抽题
def _session(user_id: int, qids: list) -> str:
    return exams_api._issue_exam_session(user_id, qids)


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    from shared.models.qualification import RepresentativeQualification
    tables = [User.__table__, TrainingMaterial.__table__, ExamQuestion.__table__,
              ExamRecord.__table__, RepresentativeQualification.__table__]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    db = TestSession()
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep", status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin", status="active"),
        User(id=3, username="med", full_name="医学部", phone="13800000003", role="medical", status="active"),
    ])
    db.commit()
    db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, _override_db)
    audit_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(exams_api, "write_audit_log", audit_mock)
    yield audit_mock


def _add_q(**kw):
    """建题目行。支持覆盖任意字段；未指定 review_status 时默认 approved。"""
    db = TestSession()
    defaults = dict(
        id=kw.pop("id", 1), material_id=None, question_type="single",
        content="测试题目", options=["A", "B"], answer=[1], review_status="approved",
    )
    defaults.update(kw)
    db.add(ExamQuestion(**defaults))
    db.commit()
    db.close()
    return defaults["id"]


def test_create_question(fresh_state):
    resp = client.post("/api/v1/exams/questions", json={
        "question_type": "single", "content": "医药代表可否承担销售任务？",
        "options": ["可以", "不可以"], "answer": [1], "material_id": None,
    }, headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "pending"
    assert "answer" not in body["data"]  # 默认不暴露答案
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_create_question_rejects_rep():
    resp = client.post("/api/v1/exams/questions", json={
        "question_type": "single", "content": "x", "options": ["A", "B"], "answer": [1],
    }, headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def test_create_question_validates():
    resp = client.post("/api/v1/exams/questions", json={
        "question_type": "bad", "content": "x", "options": ["A"], "answer": [0],
    }, headers=_token(2, "admin"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_list_questions_filters_status():
    _add_q(id=1, review_status="approved")
    _add_q(id=2, review_status="pending")
    resp = client.get("/api/v1/exams/questions?review_status=pending", headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["id"] == 2
    assert body["data"]["items"][0]["answer"] == [1]  # 审核人可见答案


def test_list_questions_exposes_answer_to_admin():
    _add_q(id=1, question_type="multiple", content="多选", options=["A", "B", "C"], answer=[0, 2], review_status="approved")
    resp = client.get("/api/v1/exams/questions", headers=_token(2, "admin"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["answer"] == [0, 2]


def test_review_approve(fresh_state):
    _add_q(id=1, review_status="pending")
    resp = client.post("/api/v1/exams/questions/1/review", json={"verdict": "approve"},
                       headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "approved"
    assert body["data"]["reviewed_by"] == 3
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()


def test_review_reject_requires_reason():
    _add_q(id=1, review_status="pending")
    resp = client.post("/api/v1/exams/questions/1/review", json={"verdict": "reject"},
                       headers=_token(3, "medical"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_review_reject_saves_reason(fresh_state):
    _add_q(id=1, review_status="pending")
    resp = client.post("/api/v1/exams/questions/1/review",
                       json={"verdict": "reject", "reason": "选项有歧义"},
                       headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "rejected"
    assert body["data"]["review_reason"] == "选项有歧义"


def test_review_not_pending_rejected():
    _add_q(id=1, review_status="approved")
    resp = client.post("/api/v1/exams/questions/1/review", json={"verdict": "approve"},
                       headers=_token(3, "medical"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_update_rejected_resets_to_pending():
    _add_q(id=1, review_status="rejected", review_reason="选项有歧义", reviewed_by=3)
    resp = client.put("/api/v1/exams/questions/1",
                      json={"question_type": "single", "content": "修正后的题目",
                            "options": ["A", "B"], "answer": [0]},
                      headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["review_status"] == "pending"
    assert body["data"]["review_reason"] is None


def test_ai_generate_returns_drafts(fresh_state, monkeypatch):
    from app.services import qwen_client as qc

    fake = {
        "questions": [
            {"question_type": "single", "content": "AI 生成的题目？",
             "options": ["A", "B", "C", "D"], "answer": [2]},
        ]
    }
    monkeypatch.setattr(qc.QwenExamClient, "generate_questions", lambda self, *a, **k: fake)

    db = TestSession()
    db.add(TrainingMaterial(id=1, title="办法", material_type="regulation", content="正文", status="active"))
    db.commit()
    db.close()

    resp = client.post("/api/v1/exams/questions/ai-generate",
                       json={"material_id": 1, "count": 1, "question_type": "single"},
                       headers=_token(3, "medical"))
    body = resp.json()
    assert body["code"] == 0
    assert isinstance(body["data"], list)
    assert body["data"][0]["content"] == "AI 生成的题目？"
    assert body["data"][0]["answer"] == [2]


def test_ai_generate_rejects_rep():
    resp = client.post("/api/v1/exams/questions/ai-generate",
                       json={"material_id": 1}, headers=_token(1, "rep"))
    assert resp.status_code == 403
    assert resp.json()["code"] == 3000


def _add_qualification(representative_id: int):
    db = TestSession()
    from shared.models.qualification import RepresentativeQualification
    db.add(RepresentativeQualification(
        representative_id=representative_id, education_cert="https://oss/edu.pdf",
        audit_status="approved", filing_number="F-1",
    ))
    db.commit()
    db.close()


def test_start_returns_approved_questions_no_answer():
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    _add_q(id=2, question_type="single", content="q2", options=["A", "B"], answer=[0], review_status="pending")
    resp = client.post("/api/v1/exams/start", json={"question_count": 10}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    items = body["data"]["questions"]
    assert len(items) == 1  # 只抽 approved
    assert items[0]["content"] == "q1"
    assert "answer" not in items[0]
    # H-1：开考同时签发考试会话 token，交卷必须携带
    assert body["data"]["session_token"]
    assert body["data"]["expires_in"] > 0
    # 会话绑定的题目集合 = 本次试卷
    sess = jwt.decode(body["data"]["session_token"], os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert sess["scope"] == "exam"
    assert sess["uid"] == 1
    assert sess["qids"] == [1]


def test_start_requires_rep():
    resp = client.post("/api/v1/exams/start", json={}, headers=_token(2, "admin"))
    assert resp.status_code == 403


def test_submit_scores_and_writes_record(fresh_state):
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    _add_q(id=2, question_type="multiple", content="q2", options=["A", "B", "C"], answer=[0, 2], review_status="approved")
    db = TestSession()
    _add_qualification(1)
    db.close()

    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},
        {"question_id": 2, "selected": [0, 2]},
    ], "session_token": _session(1, [1, 2])}, headers=_token(1, "rep"))
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["question_count"] == 2
    assert data["correct_count"] == 2
    assert data["score"] == 100
    assert data["passed"] is True
    audit_mock = fresh_state
    audit_mock.assert_awaited_once()

    # 回写 representative_qualifications
    from shared.models.qualification import RepresentativeQualification
    db = TestSession()
    qual = db.query(RepresentativeQualification).filter_by(representative_id=1).first()
    assert qual.compliance_exam_score == 100
    assert qual.compliance_training_completed is True
    db.close()


def test_submit_partial_score():
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    _add_q(id=2, question_type="single", content="q2", options=["A", "B"], answer=[0], review_status="approved")
    db = TestSession()
    _add_qualification(1)
    db.close()

    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},
        {"question_id": 2, "selected": [1]},  # 错
    ], "session_token": _session(1, [1, 2])}, headers=_token(1, "rep"))
    body = resp.json()
    data = body["data"]
    assert data["score"] == 50
    assert data["passed"] is False


def test_submit_unknown_question_rejected():
    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 999, "selected": [0]},
    ], "session_token": _session(1, [999])}, headers=_token(1, "rep"))
    assert resp.status_code == 404
    assert resp.json()["code"] == 4000


def test_submit_rejects_duplicate_question():
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},
        {"question_id": 1, "selected": [0]},
    ], "session_token": _session(1, [1, 1])}, headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


# ==================== H-1（2026-08-24 审查修复）：考试会话绑定 ====================

def test_submit_requires_session_token():
    """无 session_token 直接交卷 → 参数错误（此前的绕过路径之一）"""
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},
    ]}, headers=_token(1, "rep"))
    assert resp.status_code == 400
    assert resp.json()["code"] == 1000


def test_submit_rejects_self_picked_questions():
    """核心绕过路径：会话抽了 2 题，只挑 1 道已知正确答案的题交卷 → 拒绝，
    且不写考试记录、不置 training_completed"""
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    _add_q(id=2, question_type="single", content="q2", options=["A", "B"], answer=[0], review_status="approved")
    db = TestSession()
    _add_qualification(1)
    db.close()

    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},  # 只交会话里的一道
    ], "session_token": _session(1, [1, 2])}, headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001

    from shared.models.qualification import RepresentativeQualification
    db = TestSession()
    assert db.query(ExamRecord).count() == 0
    qual = db.query(RepresentativeQualification).filter_by(representative_id=1).first()
    assert qual.compliance_training_completed is False
    db.close()


def test_submit_rejects_foreign_session():
    """别人的会话 token 交卷 → 拒绝（uid 不匹配）"""
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},
    ], "session_token": _session(2, [1])}, headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_submit_rejects_expired_session(monkeypatch):
    """过期会话 → 拒绝（含重放旧会话）"""
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    # 用负 TTL 签发一个已过期的会话
    monkeypatch.setattr(exams_api, "_EXAM_SESSION_TTL_SECONDS", -1)
    token = _session(1, [1])
    monkeypatch.setattr(exams_api, "_EXAM_SESSION_TTL_SECONDS", 2 * 60 * 60)
    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},
    ], "session_token": token}, headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_submit_rejects_login_token_as_session():
    """拿登录 JWT 冒充会话 token → 拒绝（scope 不符）"""
    _add_q(id=1, question_type="single", content="q1", options=["A", "B"], answer=[1], review_status="approved")
    resp = client.post("/api/v1/exams/submit", json={"answers": [
        {"question_id": 1, "selected": [1]},
    ], "session_token": create_token(user_id=1, username="rep01", role="rep")}, headers=_token(1, "rep"))
    assert resp.status_code == 422
    assert resp.json()["code"] == 4001


def test_records_me_and_admin_list():
    db = TestSession()
    db.add(ExamRecord(id=1, representative_id=1, question_count=2, correct_count=2, score=100, passed=True))
    db.add(ExamRecord(id=2, representative_id=1, question_count=2, correct_count=1, score=50, passed=False))
    db.commit()
    db.close()

    me = client.get("/api/v1/exams/records/me", headers=_token(1, "rep"))
    assert me.json()["data"]["total"] == 2
    all_ = client.get("/api/v1/exams/records", headers=_token(2, "admin"))
    assert all_.json()["data"]["total"] == 2
