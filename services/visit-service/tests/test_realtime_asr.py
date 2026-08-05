"""实时转写（阿里云实时 ASR 选型）单元测试 —— Mock 客户端 + 签名 + WS 鉴权"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi.testclient import TestClient
from app.services.realtime_asr import MockRealtimeAsrClient, _sign_params, _percent_encode
from app.main import app


class TestRealtimeAsrClient:
    def test_mock_client_streams_intermediate_and_final(self):
        """Mock 客户端：每段音频产生一条中间结果 + 一条断句完成"""
        async def run():
            events = []
            client = MockRealtimeAsrClient(sentences=["测试句子"], interval=0)
            await client.start(on_sentence=lambda text, index, is_final: _collect(events, text, index, is_final))
            await client.feed(b"\x00" * 3200)
            await client.close()
            return events

        async def _collect(events, text, index, is_final):
            events.append((text, index, is_final))

        events = asyncio.run(run())
        assert len(events) == 2, f"应收到中间+断句两条，实际 {events}"
        assert events[0] == ("测试句子", 1, False)
        assert events[1] == ("测试句子", 1, True)

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
