"""
通义千问客户端（OpenAI 兼容接口）

用于医生画像 AI 生成。与 specialist-service 中的实现保持一致。
"""

import os
import logging
from typing import List, Dict
from openai import OpenAI

logger = logging.getLogger(__name__)


class QwenClient:
    """通义千问客户端"""

    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY", ""),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
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
