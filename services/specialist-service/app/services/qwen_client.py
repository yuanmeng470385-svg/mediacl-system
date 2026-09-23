"""
通义千问客户端（OpenAI 兼容接口）

百炼 App 不可用时的降级方案：直接调通义千问生成答案（不带知识库检索）。
"""

import os
import logging
from typing import List, Dict

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)


class QwenClient:
    """通义千问客户端"""

    def __init__(self):
        # G3（2026-08-13）：显式超时 + 单次重试。SDK 默认 600s 读超时 × 2 次重试，
        # 降级路径（answer_generator 用 asyncio.to_thread 包裹本同步调用）在网络
        # 异常时会长时间悬挂；qwen-max 常规回答 30s 读超时 + 10s 连接超时足够。
        self.client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=httpx.Timeout(30.0, connect=10.0),
            max_retries=1,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ) -> dict:
        """
        同步调用通义千问

        Args:
            timeout: 本请求超时（秒）。默认 30.0 与 __init__ 的 client 级
                httpx.Timeout(30.0, connect=10.0) 一致——存量调用不传即零影响；
                陪练评分/风格提取等同步长链路按需放宽（决策 11，网关已 120s carve-out）。

        Returns:
            {"content": "...", "usage": {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}}
        """
        model = model or os.getenv("QWEN_MAX_MODEL", "qwen-max")
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=httpx.Timeout(timeout, connect=10.0),
            )
            return {
                "content": response.choices[0].message.content,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                }
            }
        except Exception as e:
            logger.error(f"通义千问调用失败: {e}")
            raise
    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ):
        """同步流式生成器：逐块 yield 增量文本。

        D1 当年删掉的 chat_stream 复活（2026-09-23）：多租户部署后线上分身大多
        bailian_app_id 为空，qwen 降级从"兜底"变成主路径——同步整段返回导致
        WS 只能发一个 delta，App 端流式名存实亡。调用方需放 worker 线程跑
        （answer_generator._astream_fallback）。
        """
        model = model or os.getenv("QWEN_MAX_MODEL", "qwen-max")
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        for chunk in response:
            if not chunk.choices:
                continue
            text = getattr(chunk.choices[0].delta, "content", None)
            if text:
                yield text

    # D1（2026-08-13）：chat_stream 曾按死代码删除 —— 2026-09-23 随流式降级复活（见上）
    # （流式走百炼 bailian_client.chat_stream；本客户端只服务降级同步路径）。
