"""QwenClient 配置回归（G3 2026-08-13）

降级路径在 answer_generator 中经 asyncio.to_thread 包裹的同步 SDK 调用，
客户端必须显式超时 + 限制重试：SDK 默认 600s 读超时 × 2 次重试会在网络
异常时让 worker 线程长时间悬挂。
"""


class _RecordingOpenAI:
    """记录 OpenAI 构造参数，不发起任何请求"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_qwen_client_explicit_timeout_and_retries(monkeypatch):
    from app.services.qwen_client import QwenClient

    created = {}

    class _Recorder:
        def __init__(self, **kwargs):
            created.update(kwargs)

    monkeypatch.setattr("app.services.qwen_client.OpenAI", _Recorder)
    QwenClient()
    assert "timeout" in created
    timeout = created["timeout"]
    # httpx.Timeout(30, connect=10)：读超时 30s、连接超时 10s（SDK 默认 600s 过久）
    assert timeout.read == 30.0
    assert timeout.connect == 10.0
    assert created["max_retries"] == 1
