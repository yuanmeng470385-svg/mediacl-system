"""
通义千问客户端（OpenAI 兼容接口）

百炼 App 不可用时的降级方案：直接调通义千问生成答案（不带知识库检索）。
"""

import os
import logging
from typing import List, Dict, Generator
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
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> dict:
        """
        同步调用通义千问

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
        **kwargs
    ) -> Generator[str, None, None]:
        """流式调用通义千问"""
        model = model or os.getenv("QWEN_MAX_MODEL", "qwen-max")
        try:
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                **kwargs
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as e:
            logger.error(f"通义千问流式调用失败: {e}")
            raise
