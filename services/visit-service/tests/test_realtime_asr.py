"""实时转写（阿里云实时 ASR 选型）单元测试 —— Mock 客户端 + 签名 + WS 鉴权 + 说话人分离"""
import asyncio
import json
import sys
import os
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.services.realtime_asr import (
    MockRealtimeAsrClient, RealtimeAsrClient, _sign_params, _percent_encode,
)
from app.api.asr_ws import _map_speaker
from app.main import app
from shared.common.auth import create_token


class TestRealtimeAsrClient:
    def test_mock_client_streams_intermediate_and_final(self):
        """Mock 客户端：每段音频产生一条中间结果 + 一条断句完成（带 speaker=rep）"""
        async def run():
            events = []
            client = MockRealtimeAsrClient(sentences=["测试句子"], interval=0)
            await client.start(on_sentence=lambda text, index, is_final, speaker=None: _collect(events, text, index, is_final, speaker))
            await client.feed(b"\x00" * 3200)
            await client.close()
            return events

        async def _collect(events, text, index, is_final, speaker):
            events.append((text, index, is_final, speaker))

        events = asyncio.run(run())
        assert len(events) == 2, f"应收到中间+断句两条，实际 {events}"
        assert events[0] == ("测试句子", 1, False, "rep")
        assert events[1] == ("测试句子", 1, True, "rep")

    def test_sign_params_deterministic(self):
        """阿里云 RPC 签名：相同参数输出一致（防未来改动破坏 token 换取）"""
        params = {
            "AccessKeyId": "test-ak",
            "Action": "CreateToken",
            "Format": "JSON",
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": "abc123",
            "SignatureVersion": "1.0",
            "Timestamp": "2026-08-04T00:00:00Z",
            "Version": "2019-02-28",
        }
        s1 = _sign_params(params, "test-sk")
        s2 = _sign_params(params, "test-sk")
        assert s1 == s2
        assert len(s1) > 10

    def test_percent_encode(self):
        """百分号编码：字母数字与 ~ . - _ 不转义，其余大写转义"""
        assert _percent_encode("a-b.c~d_e") == "a-b.c~d_e"
        assert _percent_encode(" ") == "%20"
        assert _percent_encode("中文") == "%E4%B8%AD%E6%96%87"

    def test_next_message_id_is_32_hex_uuid(self):
        """NLS 要求 message_id 为 32 位十六进制 UUID（每次唯一）：
        真实联调发现 "task_id-N" 格式被网关拒绝（40000002 MESSAGE_INVALID）"""
        import re
        client = RealtimeAsrClient(app_key="test-appkey")
        for _ in range(5):
            mid = client._next_message_id()
            assert re.fullmatch(r"[0-9a-f]{32}", mid), f"message_id 应为 32 位 hex，实际 {mid!r}"
        # 每次请求唯一
        assert len({client._next_message_id() for _ in range(100)}) == 100


class TestAsrWebSocket:
    def test_ws_rejects_without_token(self):
        """WS 端点：query 与首帧 auth 都没有 token → 4401 关闭（B5 首帧鉴权协议）

        B7（2026-08-13）：旧实现 assert False 被外层 except 吞掉（测试恒绿、失去断言
        价值）；改为显式断言 receive 抛 WebSocketDisconnect 且关闭码 4401。
        """
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                # 新协议：连接后先发 auth 帧（token 为空 → 服务端关 4401）
                ws.send_text(json.dumps({"type": "auth", "token": ""}))
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    ws.receive_json()  # 服务端 close(4401) → WebSocketDisconnect
            assert exc_info.value.code == 4401, f"关闭码应为 4401，实际 {exc_info.value.code}"


class TestSpeakerSeparation:
    """需求 2.2.2 双方分离（2026-08-27 修正）：

    NLS SpeechTranscriber 实时识别不支持说话人分离（协议文档参数表/事件无
    speaker 字段），enable_speaker_identity/speaker_diarization 为无效参数已移除。
    双方分离改由移动端手动标注（REST transcript 提交 speaker），ASR 帧缺省 rep。
    """

    def test_start_payload_has_no_speaker_separation(self, monkeypatch):
        """StartTranscription 参数：不含（已移除的）说话人分离参数"""
        client = RealtimeAsrClient(app_key="test-appkey")
        payload = client._build_start_payload()
        assert payload["enable_intermediate_result"] is True  # 原有参数不受影响
        assert "enable_speaker_identity" not in payload
        assert "speaker_diarization" not in payload

    def test_mock_client_pushes_speaker_rep(self):
        """Mock 客户端：回推帧带 speaker="rep"（无真实说话人信息，固定 rep）"""
        async def run():
            events = []
            client = MockRealtimeAsrClient(sentences=["测试句子"], interval=0)
            await client.start(
                on_sentence=lambda text, index, is_final, speaker=None: _collect(events, text, index, is_final, speaker),
            )
            await client.feed(b"\x00" * 3200)
            await client.close()
            return events

        async def _collect(events, text, index, is_final, speaker):
            events.append((text, index, is_final, speaker))

        events = asyncio.run(run())
        assert len(events) == 2
        assert all(ev[3] == "rep" for ev in events), f"Mock 回推应固定 rep，实际 {events}"

    def test_event_speaker_passthrough(self):
        """NLS 事件 speaker 透传优先级：speaker_id → channel → 句首值"""
        assert RealtimeAsrClient._event_speaker({"speaker_id": 1, "channel": 9}, "s0") == 1
        assert RealtimeAsrClient._event_speaker({"channel": 9}, "s0") == 9
        assert RealtimeAsrClient._event_speaker({}, "s0") == "s0"
        # 0 是合法 speaker_id，不是缺失
        assert RealtimeAsrClient._event_speaker({"speaker_id": 0}, "s0") == 0


class TestSpeakerMapping:
    """回推帧 speaker 字段映射（asr_ws）：有真实信息映射，无则缺省 rep"""

    def test_map_speaker_defaults_to_rep(self):
        assert _map_speaker(None) == "rep"
        assert _map_speaker("未知") == "rep"
        assert _map_speaker(99) == "rep"

    def test_map_speaker_nls_ids(self):
        assert _map_speaker(0) == "rep"
        assert _map_speaker("0") == "rep"
        assert _map_speaker(1) == "doctor"
        assert _map_speaker("1") == "doctor"

    def test_map_speaker_passthrough(self):
        assert _map_speaker("rep") == "rep"
        assert _map_speaker("doctor") == "doctor"


# ---------- WS 会话级测试（NLS_MOCK=1 + 假 Session/合规，不连真实服务） ----------

class _FakeAsrSession:
    """假 session：query(...).filter(...).first() → 归属校验通过的记录

    B4（2026-08-13）：连接建立即查拜访状态 —— 记录带 status/ai_summary 字段
    （进行中），缺失字段会触发状态守卫 AttributeError。
    """

    def __init__(self, user_id: int = 7):
        self._user_id = user_id
        self.is_active = True

    def query(self, model):
        return _FakeAsrQuery(self._user_id, model)

    def close(self):
        pass


class _FakeAsrQuery:
    def __init__(self, user_id: int, model=None):
        self._user_id = user_id
        self._model = model

    def filter(self, *args, **kwargs):
        return self

    def populate_existing(self):
        return self

    def first(self):
        if self._model is not None and self._model.__name__ == "User":
            # H2（2026-08-11）：asr_ws 鉴权实时查库——返回 active 用户
            return SimpleNamespace(id=self._user_id, username="rep1", role="rep", status="active")
        return SimpleNamespace(
            user_id=self._user_id, product_id=1, hcp_id=1,
            status="in_progress", ai_summary=None,
        )


class TestAsrWebSocketFlow:
    """实时转写 WS 全流程：NLS_MOCK=1，帧结构含 speaker 字段；RuntimeError 捕获"""

    def test_ws_mock_flow_frames_have_speaker(self, monkeypatch):
        """NLS_MOCK=1 会话：回推帧统一带 speaker 字段（缺省 rep），帧结构完整"""
        import logging
        from app.api import asr_ws

        monkeypatch.setattr(asr_ws, "SessionLocal", lambda: _FakeAsrSession())

        async def _fake_compliance(text, context=None):
            return {"blocked": False, "violations": [], "risk_level": "none"}
        monkeypatch.setattr(asr_ws, "check_compliance", _fake_compliance)
        monkeypatch.delenv("NLS_APPKEY", raising=False)
        monkeypatch.setenv("NLS_MOCK", "1")

        token = create_token(7, "rep1", "rep")
        with TestClient(app) as client:
            # B5 首帧鉴权：token 走首帧 auth（不再放 query）
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": token}))
                ready = ws.receive_json()
                assert ready["type"] == "ready" and ready["visit_id"] == 1
                ws.send_bytes(b"\x00" * 3200)
                f1 = ws.receive_json()  # 中间结果
                f2 = ws.receive_json()  # 断句完成
                assert f1["type"] == "sentence" and f1["final"] is False
                assert f2["type"] == "sentence" and f2["final"] is True
                assert f1["index"] == 1 and f2["index"] == 1
                # 双方分离：speaker 字段存在，缺省值为 "rep"
                assert f1["speaker"] == "rep"
                assert f2["speaker"] == "rep"
                ws.send_text(json.dumps({"type": "stop"}))
                done = ws.receive_json()
                assert done["type"] == "completed"

    def test_ws_check_later_swallows_runtime_error(self, monkeypatch, caplog):
        """后台合规推送抛 RuntimeError（连接关闭后 starlette send 场景）→ 捕获不炸"""
        import logging
        from app.api import asr_ws

        caplog.set_level(logging.INFO, logger="app.api.asr_ws")
        monkeypatch.setattr(asr_ws, "SessionLocal", lambda: _FakeAsrSession())
        monkeypatch.delenv("NLS_APPKEY", raising=False)
        monkeypatch.setenv("NLS_MOCK", "1")

        async def _compliance_raises_runtime_error(text, context=None):
            # 模拟连接关闭后 starlette send 抛的 RuntimeError（后台推送路径）
            raise RuntimeError("Cannot call 'send' once a close message has been sent")
        monkeypatch.setattr(asr_ws, "check_compliance", _compliance_raises_runtime_error)

        token = create_token(7, "rep1", "rep")
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": token}))
                ws.receive_json()  # ready
                ws.send_bytes(b"\x00" * 3200)
                ws.receive_json()  # 中间结果
                ws.receive_json()  # 断句完成 → 触发 _check_later（合规抛 RuntimeError）
            time.sleep(0.3)  # 等后台任务收尾
        assert "跳过合规推送" in caplog.text


# ---------- F3 回归（2026-08-13）：warn 级违规也推合规帧 + 落库 compliance_flags ----------

class _FakeAsrSessionWithRecord:
    """假 session：归属校验通过；记录带 status/ai_summary/compliance_flags 等真实字段

    B4 后 _FakeAsrSession 的记录也补齐 status/ai_summary（连接建立的状态守卫
    需要）；本 fake 额外支持 commit + with_for_update，供 F3 断言 compliance_flags
    落库与 B1 断言兜底落库守卫使用。
    """

    def __init__(self, user_id: int = 7):
        self._user_id = user_id
        self.is_active = True
        self.record = SimpleNamespace(
            user_id=user_id, product_id=1, hcp_id=1,
            status="in_progress", ai_summary=None, compliance_flags=None,
            conversation_transcript="",
        )

    def query(self, model):
        return _FakeAsrQueryWithRecord(self._user_id, model, self.record)

    def commit(self):
        pass

    def close(self):
        pass


class _FakeAsrQueryWithRecord:
    def __init__(self, user_id, model, record):
        self._user_id = user_id
        self._model = model
        self._record = record

    def filter(self, *args, **kwargs):
        return self

    def with_for_update(self):
        return self

    def populate_existing(self):
        return self

    def first(self):
        if self._model is not None and self._model.__name__ == "User":
            return SimpleNamespace(id=self._user_id, username="rep1", role="rep", status="active")
        return self._record


def _run_ws_warn_flow(monkeypatch, compliance_fn):
    """跑一轮 NLS_MOCK WS 会话，返回 (合规帧, session)"""
    from app.api import asr_ws
    session = _FakeAsrSessionWithRecord()
    monkeypatch.setattr(asr_ws, "SessionLocal", lambda: session)
    monkeypatch.delenv("NLS_APPKEY", raising=False)
    monkeypatch.setenv("NLS_MOCK", "1")
    monkeypatch.setattr(asr_ws, "check_compliance", compliance_fn)

    token = create_token(7, "rep1", "rep")
    compliance_frame = None
    with TestClient(app) as client:
        with client.websocket_connect("/ws/visits/1/asr") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": token}))
            ws.receive_json()  # ready
            ws.send_bytes(b"\x00" * 3200)
            for _ in range(3):
                frame = ws.receive_json()
                if frame.get("type") == "compliance":
                    compliance_frame = frame
                    break
            ws.send_text(json.dumps({"type": "stop"}))
            ws.receive_json()  # completed
        time.sleep(0.3)  # 等后台任务落库收尾
    return compliance_frame, session


class TestAsrWebSocketComplianceFrames:
    """F3：WS 实时合规帧——warn 级违规推送 + compliance_flags 落库（与 REST 同口径）"""

    def test_warn_violations_push_frame_and_persist_flags(self, monkeypatch):
        """violations 非空、blocked=False（warn 级）→ 推送合规帧（blocked=False 区分轻重）+ 落库"""

        async def _warn_compliance(text, context=None):
            return {"blocked": False, "risk_level": "medium",
                    "violations": [{"rule_code": "R002", "severity": "warn", "matched_text": text}]}

        frame, session = _run_ws_warn_flow(monkeypatch, _warn_compliance)
        assert frame is not None, "warn 级违规也应推送合规帧"
        assert frame["blocked"] is False
        assert len(frame["violations"]) == 1
        assert frame["violations"][0]["rule_code"] == "R002"
        # 落库与 REST 同口径：violations 累加、blocked 取或
        flags = session.record.compliance_flags
        assert flags is not None, "warn 级违规应落库 compliance_flags"
        assert flags["blocked"] is False
        assert len(flags["violations"]) == 1

    def test_blocked_violations_push_frame_and_persist_blocked_flag(self, monkeypatch):
        """blocked=True 路径不受重构影响：帧带 blocked=True，落库 blocked 取或"""

        async def _blocked_compliance(text, context=None):
            return {"blocked": True, "risk_level": "high",
                    "violations": [{"rule_code": "R001", "severity": "high", "matched_text": text}]}

        frame, session = _run_ws_warn_flow(monkeypatch, _blocked_compliance)
        assert frame is not None
        assert frame["blocked"] is True
        assert len(frame["violations"]) == 1
        flags = session.record.compliance_flags
        assert flags["blocked"] is True
        assert len(flags["violations"]) == 1

    def test_warn_frame_pushed_but_flags_not_appended_after_visit_ended(self, monkeypatch):
        """会话中拜访被 end（证据封存）：帧仍然推送（实时告警），但 compliance_flags 不追加

        连接时拜访仍在进行中（B4 后已结束拜访在连接建立即被拒）；会话进行中拜访被
        并发 end —— 状态守卫在每句落库时生效：帧照推、落库跳过。
        """

        async def _warn_compliance(text, context=None):
            return {"blocked": False, "risk_level": "medium",
                    "violations": [{"rule_code": "R002", "severity": "warn", "matched_text": text}]}

        from app.api import asr_ws
        session = _FakeAsrSessionWithRecord()
        monkeypatch.setattr(asr_ws, "SessionLocal", lambda: session)
        monkeypatch.delenv("NLS_APPKEY", raising=False)
        monkeypatch.setenv("NLS_MOCK", "1")
        monkeypatch.setattr(asr_ws, "check_compliance", _warn_compliance)

        token = create_token(7, "rep1", "rep")
        frame = None
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": token}))
                ws.receive_json()  # ready
                session.record.ai_summary = "真实总结已生成"  # 会话中拜访被并发 end
                ws.send_bytes(b"\x00" * 3200)
                for _ in range(3):
                    f = ws.receive_json()
                    if f.get("type") == "compliance":
                        frame = f
                        break
                ws.send_text(json.dumps({"type": "stop"}))
                ws.receive_json()  # completed
            time.sleep(0.3)
        assert frame is not None and frame["blocked"] is False
        assert session.record.compliance_flags is None, "已结束拜访不应追加合规标记"


# ---------- B4 回归（2026-08-13）：连接建立时拜访已结束/已取消 → error 帧 + 4404 ----------

class TestAsrWsVisitStateGuard:
    """B4：已封存证据的拜访拒绝开新转写会话（不开付费 NLS 会话）"""

    def test_ws_rejects_ended_visit(self, monkeypatch):
        """拜访已结束（真实总结）→ error 帧 + 4404 关闭，不收 ready"""
        from app.api import asr_ws
        session = _FakeAsrSessionWithRecord()
        session.record.ai_summary = "真实总结已生成"
        monkeypatch.setattr(asr_ws, "SessionLocal", lambda: session)

        token = create_token(7, "rep1", "rep")
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": token}))
                err = ws.receive_json()
                assert err["type"] == "error"
                assert "已结束" in err["message"]
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    ws.receive_json()
                assert exc_info.value.code == 4404, f"关闭码应为 4404，实际 {exc_info.value.code}"

    def test_ws_rejects_cancelled_visit(self, monkeypatch):
        """拜访已取消 → error 帧 + 4404 关闭"""
        from app.api import asr_ws
        from app.constants import VISIT_STATUS_CANCELLED
        session = _FakeAsrSessionWithRecord()
        session.record.status = VISIT_STATUS_CANCELLED
        monkeypatch.setattr(asr_ws, "SessionLocal", lambda: session)

        token = create_token(7, "rep1", "rep")
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": token}))
                err = ws.receive_json()
                assert err["type"] == "error"
                assert "已取消" in err["message"]
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    ws.receive_json()
                assert exc_info.value.code == 4404


# ---------- B1 回归（2026-08-13）：收尾兜底落库与主路径同守卫 ----------

class TestAsrWsFallbackPersist:
    """B1：兜底路径（last_final_text 收尾追加）加 for_update + 状态复查"""

    def test_fallback_persist_skips_ended_visit(self, monkeypatch, caplog):
        """主路径断句落库失败 → 缓冲末句；收尾兜底时拜访已结束 → 放弃追加并记日志"""
        import logging
        from app.api import asr_ws
        from app.services.realtime_asr import MockRealtimeAsrClient

        caplog.set_level(logging.INFO, logger="app.api.asr_ws")
        session = _FakeAsrSessionWithRecord()
        monkeypatch.setattr(asr_ws, "SessionLocal", lambda: session)

        async def _ok_compliance(text, context=None):
            return {"blocked": False, "violations": [], "risk_level": "none"}
        monkeypatch.setattr(asr_ws, "check_compliance", _ok_compliance)

        # is_mock=False（假 ASR 客户端）→ 断句走真实落库路径（Mock 模式不落库）
        monkeypatch.setattr(
            asr_ws, "_get_asr_client",
            lambda: (MockRealtimeAsrClient(sentences=["收尾前的末句"], interval=0), False),
        )

        calls = {"n": 0}

        def _flaky_get(db, visit_id, for_update=False):
            calls["n"] += 1
            if calls["n"] == 1:
                return session.record  # 连接建立的状态守卫（进行中，放行）
            if calls["n"] == 2:
                raise RuntimeError("simulated db failure")  # 主路径落库失败 → 缓冲
            # 收尾兜底路径：期间拜访已被 end（证据已封存）
            session.record.ai_summary = "真实总结已生成"
            return session.record

        monkeypatch.setattr(asr_ws, "VisitRepo", SimpleNamespace(get=_flaky_get))

        token = create_token(7, "rep1", "rep")
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": token}))
                ws.receive_json()  # ready
                ws.send_bytes(b"\x00" * 3200)
                ws.receive_json()  # 中间结果
                ws.receive_json()  # 断句完成（主路径落库失败 → 缓冲末句）
                ws.send_text(json.dumps({"type": "stop"}))
                ws.receive_json()  # completed（finally 兜底落库已执行）
            time.sleep(0.3)

        # 兜底路径状态守卫：已结束 → 末句不追加（证据封存），且记日志
        assert session.record.conversation_transcript == "", "已结束拜访兜底不应追加末句"
        assert "收尾兜底不追加" in caplog.text, "应记日志说明放弃追加"


# ---------- B5 回归（2026-08-13）：finish 等 TranscriptionCompleted 事件 ----------

class TestFinishWaitsForCompletion:
    """B5：finish 等 Completed 事件而非固定 sleep 0.5s（末句不丢）；超时兜底"""

    def test_finish_waits_for_completed_event(self):
        """Completed 事件晚于旧实现的固定 0.5s 才到 → finish 仍等到事件才 close"""

        async def run():
            client = RealtimeAsrClient(app_key="test-appkey")
            closed = asyncio.Event()
            queue = asyncio.Queue()

            class _FakeWs:
                def __init__(self):
                    self.sent = []

                async def send(self, data):
                    self.sent.append(data)

                async def close(self):
                    assert client._completed.is_set(), "close 应发生在 TranscriptionCompleted 事件之后"
                    closed.set()

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    try:
                        return await asyncio.wait_for(queue.get(), timeout=10)
                    except asyncio.TimeoutError:
                        raise StopAsyncIteration

            ws = _FakeWs()
            client._ws = ws
            client._listener = asyncio.create_task(client._listen(lambda t, i, f, s=None: None))
            await asyncio.sleep(0.05)  # 让 listener 进入 recv 等待

            async def _deliver():
                await asyncio.sleep(1.0)  # 晚于旧实现固定 sleep 0.5s
                await queue.put(json.dumps({"header": {"name": "TranscriptionCompleted"}, "payload": {}}))

            deliver = asyncio.create_task(_deliver())
            t0 = time.monotonic()
            await client.finish()
            elapsed = time.monotonic() - t0
            await deliver
            await client._listener
            assert closed.is_set(), "finish 后应已 close"
            assert any("StopTranscription" in str(m) for m in ws.sent)
            # 事件 1.0s 到达 → finish 约 1.0s 返回；旧实现固定 0.5s close 会提前返回
            assert elapsed >= 0.9, f"应等 Completed 事件到达才 close，实际 {elapsed:.3f}s"
            assert elapsed < 2.0, f"应在事件到达后立即 close（未撞超时兜底），实际 {elapsed:.3f}s"

        asyncio.run(run())

    def test_finish_timeout_fallback_closes(self):
        """Completed 永远不到（NLS 无响应）→ 超时兜底强制 close/cancel listener"""
        import time as _time

        async def run():
            client = RealtimeAsrClient(app_key="test-appkey")
            client.COMPLETED_TIMEOUT = 0.2  # 测试加速（生产 5s）
            closed = asyncio.Event()

            class _SilentWs:
                def __init__(self):
                    self.sent = []

                async def send(self, data):
                    self.sent.append(data)

                async def close(self):
                    closed.set()

                def __aiter__(self):
                    return self

                async def __anext__(self):
                    await asyncio.sleep(10)  # 一直等，不发 Completed
                    raise StopAsyncIteration

            client._ws = _SilentWs()
            client._listener = asyncio.create_task(client._listen(lambda t, i, f, s=None: None))
            await asyncio.sleep(0.05)
            t0 = _time.monotonic()
            await client.finish()  # 0.2s 超时兜底 → close + cancel listener
            elapsed = _time.monotonic() - t0
            assert closed.is_set(), "超时后应强制 close"
            assert elapsed < 1.0, f"超时兜底不应等满生产 5s，实际 {elapsed:.3f}s"
            await asyncio.sleep(0.05)  # 等 cancel 传播
            assert client._listener.done(), "listener 应已被 cancel"

        asyncio.run(run())


# ---------- M14 回归（2026-08-14）：ASR WS 直连 8002 的连接数/帧大小/空闲/时长限制 ----------

def _wait_until(cond, timeout=2.0, interval=0.05):
    """deadline 轮询等待条件成立（终审低5，2026-08-14）：替代固定 time.sleep(0.3) ——
    CI 高负载下服务端 handler 收尾（finally 递减计数）可能慢于固定等待导致 flaky；
    写法对齐 services/gateway/tests/test_ws_proxy.py 的 deadline 轮询。超时返回
    最后一次查询结果，由后续断言给出可读失败信息。"""
    deadline = time.monotonic() + timeout
    result = False
    while True:
        result = cond()
        if result or time.monotonic() >= deadline:
            return result
        time.sleep(interval)


class TestAsrWsLimits:
    """M14：绕过网关限流的直连端点防御 —— 全局/用户并发上限、超帧、空闲超时、时长上限"""

    @pytest.fixture(autouse=True)
    def _reset_counters(self, monkeypatch):
        """计数是模块级全局（单进程近似），用例间重置防相互污染"""
        from app.api import asr_ws
        asr_ws._asr_conn_count = 0
        asr_ws._asr_conn_by_user = {}
        yield
        asr_ws._asr_conn_count = 0
        asr_ws._asr_conn_by_user = {}

    @staticmethod
    def _patch_session(monkeypatch, asr_ws, user_id=7):
        monkeypatch.setattr(asr_ws, "SessionLocal", lambda: _FakeAsrSession(user_id=user_id))
        async def _ok_compliance(text, context=None):
            return {"blocked": False, "violations": [], "risk_level": "none"}
        monkeypatch.setattr(asr_ws, "check_compliance", _ok_compliance)
        monkeypatch.delenv("NLS_APPKEY", raising=False)
        monkeypatch.setenv("NLS_MOCK", "1")

    def test_global_connection_limit_rejects_excess(self, monkeypatch):
        """全局并发上限：超限连接收 error 帧 + 4500；连接关闭后计数释放"""
        from app.api import asr_ws
        monkeypatch.setattr(asr_ws, "MAX_ASR_CONNECTIONS", 1)
        self._patch_session(monkeypatch, asr_ws)

        token = create_token(7, "rep1", "rep")
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws1:
                ws1.send_text(json.dumps({"type": "auth", "token": token}))
                assert ws1.receive_json()["type"] == "ready"
                assert asr_ws._asr_conn_count == 1, "第一条连接应登记计数"
                # 第二条连接：全局上限（Mock 路径同样受限）
                with client.websocket_connect("/ws/visits/1/asr") as ws2:
                    ws2.send_text(json.dumps({"type": "auth", "token": token}))
                    err = ws2.receive_json()
                    assert err["type"] == "error"
                    assert "上限" in err["message"]
                    with pytest.raises(WebSocketDisconnect) as exc_info:
                        ws2.receive_json()
                    assert exc_info.value.code == 4500, f"超限关闭码应为 4500，实际 {exc_info.value.code}"
            _wait_until(lambda: asr_ws._asr_conn_count == 0)  # 等服务端 handler 收尾（finally 递减）
        assert asr_ws._asr_conn_count == 0, "连接关闭后计数应释放"
        assert asr_ws._asr_conn_by_user == {}

    def test_per_user_connection_limit(self, monkeypatch):
        """同一用户并发上限：超限拒绝；不同用户不受影响"""
        from app.api import asr_ws
        monkeypatch.setattr(asr_ws, "MAX_ASR_CONNECTIONS", 10)
        monkeypatch.setattr(asr_ws, "MAX_ASR_CONNECTIONS_PER_USER", 1)

        holder = {"uid": 7}
        monkeypatch.setattr(asr_ws, "SessionLocal", lambda: _FakeAsrSession(user_id=holder["uid"]))
        async def _ok_compliance(text, context=None):
            return {"blocked": False, "violations": [], "risk_level": "none"}
        monkeypatch.setattr(asr_ws, "check_compliance", _ok_compliance)
        monkeypatch.delenv("NLS_APPKEY", raising=False)
        monkeypatch.setenv("NLS_MOCK", "1")

        token7 = create_token(7, "rep1", "rep")
        token8 = create_token(8, "rep2", "rep")
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws1:
                ws1.send_text(json.dumps({"type": "auth", "token": token7}))
                assert ws1.receive_json()["type"] == "ready"
                # 同一用户第二条连接 → 拒绝（防单账号刷 NLS 会话）
                with client.websocket_connect("/ws/visits/1/asr") as ws2:
                    ws2.send_text(json.dumps({"type": "auth", "token": token7}))
                    err = ws2.receive_json()
                    assert err["type"] == "error"
                    assert "账号" in err["message"]
                    with pytest.raises(WebSocketDisconnect) as exc_info:
                        ws2.receive_json()
                    assert exc_info.value.code == 4500
                # 不同用户 → 放行
                holder["uid"] = 8
                with client.websocket_connect("/ws/visits/1/asr") as ws3:
                    ws3.send_text(json.dumps({"type": "auth", "token": token8}))
                    assert ws3.receive_json()["type"] == "ready"
            _wait_until(lambda: asr_ws._asr_conn_count == 0)
        assert asr_ws._asr_conn_count == 0
        assert asr_ws._asr_conn_by_user == {}

    def test_oversized_frame_rejected(self, monkeypatch):
        """超帧：error 帧 + 4500 关闭（PCM 分片 16KB 正常远小于 256KB 上限）"""
        from app.api import asr_ws
        monkeypatch.setattr(asr_ws, "MAX_FRAME_BYTES", 1024)
        self._patch_session(monkeypatch, asr_ws)

        token = create_token(7, "rep1", "rep")
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": token}))
                assert ws.receive_json()["type"] == "ready"
                ws.send_bytes(b"\x00" * 2048)  # 超过注入上限 1024
                err = ws.receive_json()
                assert err["type"] == "error"
                assert "大小" in err["message"]
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    ws.receive_json()
                assert exc_info.value.code == 4500

    def test_idle_timeout_closes_session(self, monkeypatch):
        """空闲超时：超时窗口内未收到任何帧 → error 帧（含"空闲"）+ 4500 关闭"""
        from app.api import asr_ws
        monkeypatch.setattr(asr_ws, "ASR_IDLE_TIMEOUT_SECONDS", 0.3)
        self._patch_session(monkeypatch, asr_ws)

        token = create_token(7, "rep1", "rep")
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": token}))
                assert ws.receive_json()["type"] == "ready"
                # 不再推任何帧 → 0.3s 后服务端空闲超时
                err = ws.receive_json()
                assert err["type"] == "error"
                assert "空闲超时" in err["message"]
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    ws.receive_json()
                assert exc_info.value.code == 4500
        _wait_until(lambda: asr_ws._asr_conn_count == 0)
        assert asr_ws._asr_conn_count == 0, "空闲超时关闭后计数应释放"

    def test_session_duration_cap_closes_session(self, monkeypatch):
        """会话时长上限：即使持续有帧，超时后仍关闭（防僵尸连接挂住 NLS 会话）"""
        from app.api import asr_ws
        monkeypatch.setattr(asr_ws, "ASR_SESSION_MAX_SECONDS", 0.3)
        monkeypatch.setattr(asr_ws, "ASR_IDLE_TIMEOUT_SECONDS", 90.0)
        self._patch_session(monkeypatch, asr_ws)

        token = create_token(7, "rep1", "rep")
        with TestClient(app) as client:
            with client.websocket_connect("/ws/visits/1/asr") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": token}))
                assert ws.receive_json()["type"] == "ready"
                err = ws.receive_json()  # 未推帧，时长上限（0.3s）先于空闲（90s）触发
                assert err["type"] == "error"
                assert "时长" in err["message"]
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    ws.receive_json()
                assert exc_info.value.code == 4500
        _wait_until(lambda: asr_ws._asr_conn_count == 0)
        assert asr_ws._asr_conn_count == 0
