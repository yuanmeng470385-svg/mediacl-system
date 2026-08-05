"""阿里云实时语音识别客户端（实时转写技术选型，替代听悟离线轮询）

听悟（Tingwu）是离线批处理：提交任务 + 3s 轮询（最长 300s），达不到方案要求的
"实时转写延迟 < 2s"。本模块改用阿里云实时语音识别（SpeechTranscriber）：

  - 端点：wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1?token=<临时Token>
  - 鉴权：临时 Token（AK/SK 签名换取，24h 有效，进程内缓存）
  - 协议：Text Frame = JSON 指令/事件；Binary Frame = PCM 16k 单声道音频
  - 流式：StartTranscription → TranscriptionStarted → (SentenceBegin →
    TranscriptionResultChanged* → SentenceEnd)* → StopTranscription →
    TranscriptionCompleted；enable_intermediate_result=true 时中间结果实时返回

配置（.env）：
  - NLS_APPKEY：NLS 管控台项目 Appkey（必填）
  - ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET：换取临时 Token（已有）
未配置 NLS_APPKEY 时使用 MockRealtimeAsrClient（文本模拟，开发/测试用）。
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Awaitable, Callable, Dict, Optional
from urllib.parse import quote

import httpx
import websockets

logger = logging.getLogger(__name__)

NLS_WS_URL = os.getenv("NLS_WS_URL", "wss://nls-gateway.cn-shanghai.aliyuncs.com/ws/v1")
NLS_TOKEN_URL = os.getenv("NLS_TOKEN_URL", "https://nls-meta.cn-shanghai.aliyuncs.com/api/v1/token")

# 断句完成的回调签名：async def on_sentence(text: str, index: int, is_final: bool)
SentenceHandler = Callable[[str, int, bool], Awaitable[None]]


# ==================== 临时 Token（阿里云通用 RPC 签名） ====================

def _percent_encode(value: str) -> str:
    """阿里云签名要求的百分号编码：字母数字与 ~ . - _ 不转义，其余转义为大写 %XX"""
    return quote(str(value), safe="~")

def _sign_params(params: Dict[str, str], access_key_secret: str) -> str:
    sorted_items = sorted(params.items())
    canonical = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_items)
    string_to_sign = f"GET&%2F&{_percent_encode(canonical)}"
    digest = hmac.new(access_key_secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(digest.digest()).decode("utf-8")


_token_cache: Dict[str, Dict] = {}  # {"token": str, "expire_at": float}


async def get_nls_token(force: bool = False) -> str:
    """获取 NLS 临时 Token（进程内缓存，24h 过期前复用）"""
    cached = _token_cache.get("nls")
    if cached and not force and time.time() < cached["expire_at"] - 60:
        return cached["token"]

    ak = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    sk = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    if not ak or not sk:
        raise RuntimeError("未配置 ALIYUN_ACCESS_KEY_ID/ALIYUN_ACCESS_KEY_SECRET，无法换取 NLS Token")

    params = {
        "AccessKeyId": ak,
        "Action": "CreateToken",
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Version": "2019-02-28",
    }
    params["Signature"] = _sign_params(params, sk)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(NLS_TOKEN_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    token = (data.get("Token") or {}).get("Id")
    if not token:
        raise RuntimeError(f"NLS Token 换取失败: {data}")
    _token_cache["nls"] = {
        "token": token,
        "expire_at": time.time() + 24 * 3600,
    }
    return token


# ==================== 流式转写客户端 ====================

class RealtimeAsrClient:
    """实时语音识别客户端：App 推 PCM 音频 → 转发 NLS → 增量/最终结果回调

    用法：
        client = RealtimeAsrClient()
        await client.start(on_sentence=handler)   # 建连 + StartTranscription
        await client.feed(audio_chunk)            # 循环推二进制音频
        await client.finish()                     # StopTranscription + 关闭
    """

    def __init__(self, app_key: Optional[str] = None):
        self.app_key = app_key or os.getenv("NLS_APPKEY", "")
        self._ws = None
        self._task_id = uuid.uuid4().hex
        self._message_id = 0

    def _next_message_id(self) -> str:
        self._message_id += 1
        return f"{self._task_id}-{self._message_id}"

    async def start(self, on_sentence: SentenceHandler) -> None:
        """建立连接并发送 StartTranscription。返回后即可 feed 音频。"""
        if not self.app_key:
            raise RuntimeError("未配置 NLS_APPKEY（NLS 管控台项目 Appkey）")
        token = await get_nls_token()
        self._ws = await websockets.connect(f"{NLS_WS_URL}?token={token}")

        start_msg = {
            "header": {
                "appkey": self.app_key,
                "message_id": self._next_message_id(),
                "task_id": self._task_id,
                "namespace": "SpeechTranscriber",
                "name": "StartTranscription",
            },
            "payload": {
                "format": "PCM",
                "sample_rate": 16000,
                "enable_intermediate_result": True,   # 边说边出字（关键：<2s 实时）
                "enable_punctuation_prediction": True,
                "enable_inverse_text_normalization": True,
                "max_sentence_silence": 800,
            },
        }
        await self._ws.send(json.dumps(start_msg))

        # 等待 TranscriptionStarted（服务端就绪）—— 用超时保护
        async def _wait_started() -> bool:
            while True:
                frame = await asyncio.wait_for(self._ws.recv(), timeout=10)
                if isinstance(frame, str):
                    evt = json.loads(frame)
                    name = evt.get("header", {}).get("name")
                    if name == "TranscriptionStarted":
                        logger.info(f"实时转写会话开始: task_id={self._task_id}")
                        return True
                    if name == "TaskFailed":
                        logger.error(f"NLS 启动失败: {evt}")
                        return False
                # 其他事件（如早到的 SentenceBegin）忽略，等 Started

        ready = await _wait_started()
        if not ready:
            await self.close()
            raise RuntimeError("NLS 实时转写启动失败（未收到 TranscriptionStarted）")

        # 后台任务：接收 NLS 事件并触发回调
        self._listener = asyncio.create_task(self._listen(on_sentence))

    async def _listen(self, on_sentence: SentenceHandler) -> None:
        """接收 NLS 事件：中间结果 / 断句完成 → 回调"""
        try:
            async for frame in self._ws:
                if isinstance(frame, str):
                    evt = json.loads(frame)
                    name = evt.get("header", {}).get("name")
                    payload = evt.get("payload", {})
                    if name == "TranscriptionResultChanged":
                        text = payload.get("result", "")
                        if text and on_sentence:
                            await on_sentence(text, payload.get("index", 0), False)
                    elif name == "SentenceEnd":
                        text = payload.get("result", "")
                        if text and on_sentence:
                            await on_sentence(text, payload.get("index", 0), True)
                    elif name == "TranscriptionCompleted":
                        logger.info(f"实时转写完成: task_id={self._task_id}")
                        break
                    elif name == "TaskFailed":
                        logger.error(f"NLS 转写失败: {payload}")
                        break
        except Exception as exc:
            logger.error(f"NLS 事件监听异常: {exc}")

    async def feed(self, audio_chunk: bytes) -> None:
        """推送一段 PCM 音频（16k/16bit/单声道）到 NLS"""
        if not self._ws:
            raise RuntimeError("实时转写未启动")
        await self._ws.send(audio_chunk)

    async def finish(self) -> None:
        """结束转写：发送 StopTranscription 并等待完成"""
        if not self._ws:
            return
        try:
            stop_msg = {
                "header": {
                    "appkey": self.app_key,
                    "message_id": self._next_message_id(),
                    "task_id": self._task_id,
                    "namespace": "SpeechTranscriber",
                    "name": "StopTranscription",
                },
                "payload": {},
            }
            await self._ws.send(json.dumps(stop_msg))
        except Exception as exc:
            logger.error(f"StopTranscription 发送失败: {exc}")
        # 给监听任务留一点收尾时间（Completed 事件）
        await asyncio.sleep(0.5)
        await self.close()

    async def close(self) -> None:
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if getattr(self, "_listener", None) and not self._listener.done():
            self._listener.cancel()


class MockRealtimeAsrClient:
    """实时转写 Mock —— 无 NLS_APPKEY 时使用：模拟增量结果与断句，可测桥接链路"""

    def __init__(self, sentences=None, interval: float = 0.5):
        self.sentences = sentences or [
            "本次拜访主要讨论XX注射液的临床数据",
            "医生询问了长期安全性问题",
            "我们约定了下次拜访时间",
        ]
        self.interval = interval

    async def start(self, on_sentence: SentenceHandler) -> None:
        self._on_sentence = on_sentence
        self._index = 0

    async def feed(self, audio_chunk: bytes) -> None:
        # 模拟：每推送一段音频，产生一条增量+断句
        if getattr(self, "_on_sentence", None) and self._index < len(self.sentences):
            text = self.sentences[self._index]
            self._index += 1
            await asyncio.sleep(self.interval)
            await self._on_sentence(text, self._index, False)
            await self._on_sentence(text, self._index, True)

    async def finish(self) -> None:
        pass

    async def close(self) -> None:
        pass
