"""通义千问客户端（OpenAI 兼容接口，httpx 直调 dashscope，不引 openai SDK）

用于题库 AI 出题草稿（需求 3.4(2)：AI 出题仅作辅助，人工复核后入库）。
"""
import json
import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


class QwenExamClient:
    """题库 AI 出题客户端（生成题目草稿，不落库）"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.model = model or os.getenv("QWEN_EXAM_MODEL", "qwen-turbo")
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def generate_questions(
        self,
        material_text: str,
        count: int = 5,
        question_type: str = "single",
    ) -> dict:
        """根据培训材料生成题目草稿。

        Returns:
            {"questions": [{"question_type", "content", "options", "answer"}, ...]}
        """
        if not self.api_key:
            raise ValueError("未配置 DASHSCOPE_API_KEY")
        ttype = "单选" if question_type == "single" else "判断" if question_type == "judge" else "多选"
        system = (
            "你是医药行业合规培训题库出题助手。只输出 JSON，不要输出任何其他文字。"
            "基于提供的培训材料生成题目，答案必须严格来自材料内容。"
        )
        user = (
            f"请根据以下培训材料生成 {count} 道{ttype}题。\n"
            f"题目类型：{question_type}（single 单选答案只有一个索引；multiple 多选答案多个索引；judge 判断题 options 固定为 [\"正确\",\"错误\"]）。\n"
            "输出格式（严格 JSON）：\n"
            '{"questions": [{"question_type": "single", "content": "题干", '
            '"options": ["选项A", "选项B", "选项C", "选项D"], "answer": [0]}]}\n'
            "answer 是正确选项在 options 中的索引（0 起）数组。判断题 options 用 [\"正确\",\"错误\"]，answer [0] 或 [1]。\n"
            f"培训材料如下：\n<user_content>{material_text[:4000]}</user_content>"
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
        }
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return self._parse_json(text)

    def _parse_json(self, text: str) -> dict:
        """从 LLM 输出里提取 JSON（容忍 ```json 代码块包裹）"""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("AI 输出未包含 JSON 对象")
        return json.loads(cleaned[start:end + 1])
