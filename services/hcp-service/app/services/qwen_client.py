"""
通义千问客户端（OpenAI 兼容接口）

用于医生画像 AI 生成。与 specialist-service 中的实现保持一致。
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
        # I1 修复（2026-08-13）：显式超时。OpenAI SDK 默认 600s，画像生成经
        # asyncio.to_thread 在线程池同步阻塞 —— 慢响应会占线程 + DB 连接长达
        # 10 分钟，30+ 并发可耗尽资源，且降级路径只覆盖异常、不覆盖慢响应。
        # 这里收紧为读超时 30s / 连接超时 10s、最多重试 1 次：真机画像生成
        # ~8s 远小于 30s，超时走 ProfileGenerator 的 degraded 降级（基础数据）。
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
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> dict:
        """同步调用通义千问

        Returns:
            {"content": "...", "usage": {...}}
        """
        model = model or os.getenv("QWEN_MAX_MODEL", "qwen-max")
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return {
            "content": response.choices[0].message.content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
        }
