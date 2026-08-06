"""实时转写（阿里云实时 ASR 选型）单元测试 —— Mock 客户端 + 签名 + WS 鉴权 + 说话人分离"""
import asyncio
import json
import sys
import os
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi.testclient import TestClient
from app.services.realtime_asr import (
    MockRealtimeAsrClient, RealtimeAsrClient, nls_speaker_enabled, _sign_params, _percent_encode,
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


class TestAsrWebSocket:
    def test_ws_rejects_without_token(self):
        """WS 端点：无 token 拒绝连接（握手阶段拒绝）"""
        with TestClient(app) as client:
            try:
                with client.websocket_connect("/ws/visits/1/asr"):
                    assert False, "无 token 不应连接成功"
            except Exception:
                pass  # 握手被拒绝（WebSocketDisconnect / 403），符合预期


class TestSpeakerSeparation:
    """需求 2.2.2 双方分离：NLS_SPEAKER_ENABLED 配置 + speaker 信息透传"""

    def test_nls_speaker_enabled_parsing(self, monkeypatch):
        """NLS_SPEAKER_ENABLED env 解析：1/true/yes/on 开启，其余关闭（默认 false）"""
        monkeypatch.delenv("NLS_SPEAKER_ENABLED", raising=False)
        assert nls_speaker_enabled() is False
        for v in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("NLS_SPEAKER_ENABLED", v)
            assert nls_speaker_enabled() is True, f"值 {v!r} 应视为开启"
        monkeypatch.setenv("NLS_SPEAKER_ENABLED", "0")
        assert nls_speaker_enabled() is False

    def test_start_payload_speaker_params(self, monkeypatch):
        """StartTranscription 参数：默认不带说话人分离；开启后带 enable_speaker_identity 等"""
        client = RealtimeAsrClient(app_key="test-appkey")
        monkeypatch.delenv("NLS_SPEAKER_ENABLED", raising=False)
        payload = client._build_start_payload()
        assert payload["enable_intermediate_result"] is True  # 原有参数不受影响
        assert "enable_speaker_identity" not in payload
        assert "speaker_diarization" not in payload
        monkeypatch.setenv("NLS_SPEAKER_ENABLED", "1")
        payload = client._build_start_payload()
        assert payload["enable_speaker_identity"] is True
        assert payload["speaker_diarization"] == "speaker_change_detection"

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
    """假 session：query(...).filter(...).first() → 归属校验通过的记录"""

    def __init__(self, user_id: int = 7):
        self._user_id = user_id
        self.is_active = True

    def query(self, model):
        return _FakeAsrQuery(self._user_id)

    def close(self):
        pass


class _FakeAsrQuery:
    def __init__(self, user_id: int):
        self._user_id = user_id

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return SimpleNamespace(user_id=self._user_id, product_id=1, hcp_id=1)


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
            with client.websocket_connect(f"/ws/visits/1/asr?token={token}") as ws:
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
            with client.websocket_connect(f"/ws/visits/1/asr?token={token}") as ws:
                ws.receive_json()  # ready
                ws.send_bytes(b"\x00" * 3200)
                ws.receive_json()  # 中间结果
                ws.receive_json()  # 断句完成 → 触发 _check_later（合规抛 RuntimeError）
            time.sleep(0.3)  # 等后台任务收尾
        assert "跳过合规推送" in caplog.text
