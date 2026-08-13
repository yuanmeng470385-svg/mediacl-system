"""通义千问客户端（OpenAI 兼容接口）— 异议识别语义分析"""
import os
import logging
from typing import List, Dict
import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)


class QwenClient:
    """通义千问客户端"""

    def __init__(self):
        # F1（2026-08-13）：显式超时 + 限制重试。SDK 默认读超时 600s × 重试 2 次，
        # 且所有调用经 asyncio.to_thread 进入默认线程池（最多 32 线程）——挂死请求
        # 会把线程池占满拖垮整个事件循环。60s 读超时对 qwen-max 2000 token 生成
        # 足够宽裕；重试 1 次防瞬时网络抖动，不放大挂死窗口。
        self.client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=httpx.Timeout(60, connect=10),
            max_retries=1,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> dict:
        """同步调用通义千问"""
        model = model or os.getenv("QWEN_PLUS_MODEL", "qwen-plus")
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
