"""QwenClient 超时配置回归（I1，2026-08-13）

OpenAI SDK 默认超时 600s：画像生成经 asyncio.to_thread 在线程池同步阻塞，
慢响应会占线程 + DB 连接长达 10 分钟，30+ 并发可耗尽资源；降级路径只覆盖
异常、不覆盖慢响应。修复后构造时显式收紧超时（读 30s / 连接 10s）并限制
重试 1 次，超时抛异常后由 ProfileGenerator 的 degraded 降级兜底。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.qwen_client import QwenClient  # noqa: E402


def test_client_uses_explicit_timeout_and_retries():
    """构造的 OpenAI 客户端：读超时 30s / 连接超时 10s / max_retries=1（非 SDK 默认 600s/2 次）"""
    qwen = QwenClient()
    assert qwen.client.max_retries == 1

    # openai SDK 将 timeout 传给底层 httpx.Client（_client.timeout 即配置值）
    timeout = qwen.client._client.timeout
    assert timeout.read == 30.0
    assert timeout.connect == 10.0
