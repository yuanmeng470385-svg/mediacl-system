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
  - NLS_SPEAKER_ENABLED：1 时开启说话人分离（需求 2.2.2"双方分离"，默认关闭）
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

# 断句完成的回调签名：async def on_sentence(text: str, index: int, is_final: bool, speaker=None)
# speaker：说话人信息（Mock 固定 "rep"；真实 NLS 为 speaker_id/channel 原始值，由上层映射）
SentenceHandler = Callable[[str, int, bool, Optional[str]], Awaitable[None]]


def nls_speaker_enabled() -> bool:
    """NLS_SPEAKER_ENABLED → 是否开启说话人分离（1/true/yes/on 视为开启，默认关闭）"""
    return os.getenv("NLS_SPEAKER_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


# ==================== 临时 Token（阿里云通用 RPC 签名） ====================

def _percent_encode(value: str) -> str:
    """阿里云签名要求的百分号编码：字母数字与 ~ . - _ 不转义，其余转义为大写 %XX"""
    return quote(str(value), safe="~")

def _sign_params(params: Dict[str, str], access_key_secret: str) -> str:
    sorted_items = sorted(params.items())
    canonical = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_items)
    string_to_sign = f"GET&%2F&{_percent_encode(canonical)}"
    # 阿里云 RPC v1 签名规范：HMAC 密钥 = AccessKeySecret + "&"
    digest = hmac.new((access_key_secret + "&").encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1)
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


def nls_token_expire_at() -> Optional[float]:
    """当前进程缓存的 NLS token 过期时刻（epoch 秒）；尚未换过 token 返回 None"""
    cached = _token_cache.get("nls")
    return cached["expire_at"] if cached else None


# ==================== 流式转写客户端 ====================

class RealtimeAsrClient:
    """实时语音识别客户端：App 推 PCM 音频 → 转发 NLS → 增量/最终结果回调

    用法：
        client = RealtimeAsrClient()
        await client.start(on_sentence=handler)   # 建连 + StartTranscription
        await client.feed(audio_chunk)            # 循环推二进制音频
        await client.finish()                     # StopTranscription + 关闭
    """

    # B5（2026-08-13）：finish 等待 TranscriptionCompleted 的超时上限（秒）。
    # NLS 无响应/已断连时兜底强制收尾；测试可下调此值加速超时用例
    COMPLETED_TIMEOUT = 5.0

    def __init__(self, app_key: Optional[str] = None):
        self.app_key = app_key or os.getenv("NLS_APPKEY", "")
        self._ws = None
        self._task_id = uuid.uuid4().hex
        # 转写完成事件：listener 收到 TranscriptionCompleted（或监听终止）置位，
        # finish 等待它而非固定 sleep（B5）
        self._completed = asyncio.Event()

    def _next_message_id(self) -> str:
        # NLS 要求 message_id 为 32 位十六进制 UUID（每次请求唯一）——真实联调发现
        # "task_id-N" 格式被网关拒绝（Gateway:MESSAGE_INVALID:Invalid message id）
        return uuid.uuid4().hex

    def _build_start_payload(self) -> dict:
        """StartTranscription 请求参数（说话人分离受 NLS_SPEAKER_ENABLED 控制）"""
        payload = {
            "format": "PCM",
            "sample_rate": 16000,
            "enable_intermediate_result": True,   # 边说边出字（关键：<2s 实时）
            "enable_punctuation_prediction": True,
            "enable_inverse_text_normalization": True,
            "max_sentence_silence": 800,
        }
        if nls_speaker_enabled():
            # 说话人分离（需求 2.2.2"双方分离"）：
            #   enable_speaker_identity=true 开启说话人分离；
            #   speaker_diarization="speaker_change_detection" 按说话人变化断句
            #   （也可填 "2-8" 指定说话人数范围）。
            # 注意：参数名/取值以阿里云 NLS 实时识别（SpeechTranscriber）文档为准；
            # 无真实 NLS 环境，此处待真机确认，如与文档不符仅需改本方法。
            payload["enable_speaker_identity"] = True
            payload["speaker_diarization"] = "speaker_change_detection"
        return payload

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
            "payload": self._build_start_payload(),
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

        # B5：每个会话用新事件（防复用实例时上一会话的置位状态残留）
        self._completed = asyncio.Event()
        # 后台任务：接收 NLS 事件并触发回调
        self._listener = asyncio.create_task(self._listen(on_sentence))

    async def _listen(self, on_sentence: SentenceHandler) -> None:
        """接收 NLS 事件：中间结果 / 断句完成 → 回调（说话人信息透传）

        SentenceBegin / TranscriptionResultChanged / SentenceEnd 的 payload
        若含 speaker_id（说话人分离开启时）或 channel 信息，随回调透传，
        由上层（asr_ws）映射为 "rep"/"doctor"。
        """
        current_speaker = None  # 当前句的说话人信息（SentenceBegin 携带，结果事件兜底）
        try:
            async for frame in self._ws:
                if isinstance(frame, str):
                    evt = json.loads(frame)
                    name = evt.get("header", {}).get("name")
                    payload = evt.get("payload", {})
                    if name == "SentenceBegin":
                        current_speaker = payload.get("speaker_id")
                        if current_speaker is None:
                            current_speaker = payload.get("channel")
                    elif name == "TranscriptionResultChanged":
                        text = payload.get("result", "")
                        if text and on_sentence:
                            await on_sentence(
                                text, payload.get("index", 0), False,
                                self._event_speaker(payload, current_speaker),
                            )
                    elif name == "SentenceEnd":
                        text = payload.get("result", "")
                        if text and on_sentence:
                            await on_sentence(
                                text, payload.get("index", 0), True,
                                self._event_speaker(payload, current_speaker),
                            )
                    elif name == "TranscriptionCompleted":
                        logger.info(f"实时转写完成: task_id={self._task_id}")
                        self._completed.set()  # B5：解除 finish 的等待
                        break
                    elif name == "TaskFailed":
                        logger.error(f"NLS 转写失败: {payload}")
                        self._completed.set()  # B5：失败不会再有 Completed，提前解除等待
                        break
        except Exception as exc:
            logger.error(f"NLS 事件监听异常: {exc}")
        finally:
            # B5：监听以任何方式终止（正常完成/失败/断连）都解除 finish 的等待，
            # 防连接已断时 finish 空等满超时
            self._completed.set()

    @staticmethod
    def _event_speaker(payload: dict, fallback):
        """事件 payload 中的说话人信息：speaker_id 优先，channel 兜底，再退回句首值"""
        speaker = payload.get("speaker_id")
        if speaker is None:
            speaker = payload.get("channel")
        if speaker is None:
            speaker = fallback
        return speaker

    async def feed(self, audio_chunk: bytes) -> None:
        """推送一段 PCM 音频（16k/16bit/单声道）到 NLS"""
        if not self._ws:
            raise RuntimeError("实时转写未启动")
        await self._ws.send(audio_chunk)

    async def finish(self) -> None:
        """结束转写：发送 StopTranscription 并等待 TranscriptionCompleted 再关闭

        B5（2026-08-13）：旧实现发完 StopTranscription 固定 sleep 0.5s 后 close ——
        末句的 SentenceEnd/TranscriptionCompleted 晚于 0.5s 到达时会被截断丢句；
        改为事件等待（listener 收到 Completed 置位），COMPLETED_TIMEOUT 超时兜底
        后仍 close/cancel listener 强制收尾。
        """
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
        try:
            await asyncio.wait_for(self._completed.wait(), timeout=self.COMPLETED_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(
                f"等待 TranscriptionCompleted 超时（{self.COMPLETED_TIMEOUT}s），强制收尾: task_id={self._task_id}"
            )
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
        # 模拟：每推送一段音频，产生一条增量+断句（无真实说话人信息 → 固定 rep）
        if getattr(self, "_on_sentence", None) and self._index < len(self.sentences):
            text = self.sentences[self._index]
            self._index += 1
            await asyncio.sleep(self.interval)
            await self._on_sentence(text, self._index, False, "rep")
            await self._on_sentence(text, self._index, True, "rep")

    async def finish(self) -> None:
        pass

    async def close(self) -> None:
        pass
