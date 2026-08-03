"""
答案生成器 — 核心业务流水线

流程：
  用户提问
  → compliance_client 合规预检（问题是否违规）
  → bailian_client 百炼 App 对话（内部完成知识检索+LLM生成）
  → 百炼不可用时降级到 qwen_client 直调通义千问
  → compliance_client 合规审核 AI 答案
  → audit_client 审计日志
  → 返回 {answer, citations, evidence_level, ...}
"""

import time
import re
import uuid
import logging
from typing import Dict, Optional

from app.services.bailian_client import BailianClient, BailianException
from app.services.qwen_client import QwenClient
from app.services.compliance_client import check_compliance
from app.services.audit_client import write_audit_log
from app.models.specialist import Specialist

logger = logging.getLogger(__name__)


class AnswerGenerator:
    """答案生成器"""

    def __init__(self):
        self.bailian = BailianClient()
        self.qwen = QwenClient()

    async def generate(
        self,
        question: str,
        specialist: Specialist,
        user_id: int,
        session_id: Optional[str] = None,
    ) -> Dict:
        """
        生成回答（主流程）

        Args:
            question: 用户问题
            specialist: 数字专员 ORM 对象（含 bailian_app_id）
            user_id: 当前用户 ID
            session_id: 会话 ID（多轮对话时传入上次返回的 dialog_id）

        Returns:
            {
                "answer": "AI 回答文本",
                "citations": [],
                "evidence_level": "B",
                "session_id": "...",
                "request_id": "...",
                "latency_ms": 1234,
                "blocked": False,
                "violations": []
            }
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # ---- Step 1: 合规预检 ----
        logger.info(f"[{request_id}] 合规预检")
        question_check = await check_compliance(
            content=question,
            context={"user_id": user_id, "type": "user_input"}
        )
        if question_check.get("blocked"):
            return {
                "answer": "您的问题包含不合规内容，请调整后重试。",
                "citations": [],
                "evidence_level": None,
                "session_id": session_id,
                "request_id": request_id,
                "latency_ms": 0,
                "blocked": True,
                "violations": question_check.get("violations", []),
            }

        # ---- Step 2: 调百炼 App 生成答案（百炼内部完成知识检索+多模态理解+LLM）----
        logger.info(f"[{request_id}] 调用百炼 App: {specialist.bailian_app_id}")
        ai_prompt = None
        ai_response = None
        ai_model = "multimodal-dialog"

        try:
            bailian_result = await self.bailian.chat(
                app_id=specialist.bailian_app_id,
                prompt=question,
                session_id=session_id,
            )
            answer = bailian_result.get("text", "")
            session_id = bailian_result.get("dialog_id", session_id)
            ai_prompt = question
            ai_response = answer
        except BailianException as e:
            # ---- 降级：百炼不可用时直调通义千问 ----
            logger.warning(f"[{request_id}] 百炼调用失败，降级到通义千问: {e}")
            answer = self._fallback_generate(question, specialist)
            ai_prompt = question
            ai_response = answer
            ai_model = "qwen-max"

        # ---- Step 3: 合规审核 AI 答案 ----
        logger.info(f"[{request_id}] 合规审核答案")
        answer_check = await check_compliance(
            content=answer,
            context={"user_id": user_id, "type": "ai_output", "specialist_id": specialist.id}
        )
        if answer_check.get("blocked"):
            latency_ms = int((time.time() - start_time) * 1000)
            # 审计日志
            await write_audit_log(
                user_id=user_id,
                action="chat_blocked",
                ai_involved=True,
                ai_model=ai_model,
                ai_prompt=ai_prompt,
                ai_response=ai_response,
                compliance_result=answer_check,
                request_id=request_id,
            )
            return {
                "answer": "该问题建议直接咨询医学顾问。",
                "citations": [],
                "evidence_level": None,
                "session_id": session_id,
                "request_id": request_id,
                "latency_ms": latency_ms,
                "blocked": True,
                "violations": answer_check.get("violations", []),
            }

        # ---- Step 4: 审计日志 ----
        latency_ms = int((time.time() - start_time) * 1000)
        await write_audit_log(
            user_id=user_id,
            action="chat_response",
            resource_type="conversation",
            ai_involved=True,
            ai_model=ai_model,
            ai_prompt=ai_prompt,
            ai_response=ai_response,
            compliance_result=answer_check,
            request_id=request_id,
        )

        logger.info(f"[{request_id}] 回答完成，耗时 {latency_ms}ms")

        return {
            "answer": answer,
            "citations": [],  # 百炼暂不返回独立 citations，后续可从 RespondingContent.extra_info 解析
            "evidence_level": self._extract_evidence_level(answer),
            "session_id": session_id,
            "request_id": request_id,
            "latency_ms": latency_ms,
            "blocked": False,
            "violations": [],
        }

    # ==================== 降级方案 ====================

    def _fallback_generate(self, question: str, specialist: Specialist) -> str:
        """百炼不可用时，直接调通义千问（不带知识库检索）"""
        prompt = f"""你是{specialist.name}，医药产品 AI 学术专员。

代表问题：{question}

要求：
1. 简洁回答，不超过 300 字
2. 不确定时建议咨询医学顾问
3. 严禁承诺疗效、提及回扣、讨论医生处方量

回答："""

        try:
            result = self.qwen.chat(
                messages=[{"role": "user", "content": prompt}],
                model="qwen-max",
                temperature=0.1,
            )
            return result["content"]
        except Exception as e:
            logger.error(f"降级生成也失败: {e}")
            return "抱歉，服务暂时不可用，请稍后重试或直接咨询医学顾问。"

    # ==================== 辅助方法 ====================

    def _extract_evidence_level(self, answer: str) -> Optional[str]:
        """从回答中提取证据等级"""
        patterns = [
            r"证据等级[：:]\s*([A-D]|专家共识|未知)",
            r"【证据等级】\s*([A-D]|专家共识|未知)",
            r"证据等级[：:][^A-Za-z]*([ABCD])",
        ]
        for p in patterns:
            m = re.search(p, answer)
            if m:
                return m.group(1)
        return None
