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
from app.core.activity_registry import (
    registry, PHASE_COMPLIANCE_PRECHECK, PHASE_GENERATING, PHASE_COMPLIANCE_REVIEW,
)

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
        try:
            start_time = time.time()

            # ---- Step 1: 合规预检 ----
            registry.set_working(specialist.id, PHASE_COMPLIANCE_PRECHECK, question)
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
            registry.set_working(specialist.id, PHASE_GENERATING, question)
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
                if not answer.strip():
                    # 百炼"成功"但未产出内容（App 未发布/无检索结果/空回答）——
                    # 视为调用失败走 qwen 降级，避免下游对空 content 报 400 且用户拿到空答案
                    raise BailianException("百炼返回空答案（App 未发布或无检索结果）")
                citations = bailian_result.get("citations", [])
                session_id = bailian_result.get("dialog_id", session_id)
                ai_prompt = question
                ai_response = answer
            except BailianException as e:
                # ---- 降级：百炼不可用时直调通义千问 ----
                logger.warning(f"[{request_id}] 百炼调用失败，降级到通义千问: {e}")
                answer = self._fallback_generate(question, specialist)
                citations = []
                ai_prompt = question
                ai_response = answer
                ai_model = "qwen-max"

            # ---- Step 3: 合规审核 AI 答案 ----
            logger.info(f"[{request_id}] 合规审核答案")
            registry.set_working(specialist.id, PHASE_COMPLIANCE_REVIEW, question)
            answer_check = await check_compliance(
                content=answer,
                context={"user_id": user_id, "type": "ai_output", "specialist_id": specialist.id}
            )
            if answer_check.get("blocked"):
                latency_ms = int((time.time() - start_time) * 1000)
                from app.api.metrics import CHAT_LATENCY
                CHAT_LATENCY.observe(latency_ms / 1000.0)
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
                    "citations": citations,
                    "evidence_level": None,
                    "session_id": session_id,
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                    "blocked": True,
                    "violations": answer_check.get("violations", []),
                }

            # ---- Step 4: 审计日志 ----
            latency_ms = int((time.time() - start_time) * 1000)
            from app.api.metrics import CHAT_LATENCY
            CHAT_LATENCY.observe(latency_ms / 1000.0)
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
                "citations": citations,
                "evidence_level": self._extract_evidence_level(answer),
                "session_id": session_id,
                "request_id": request_id,
                "latency_ms": latency_ms,
                "blocked": False,
                "violations": [],
            }
        finally:
            registry.set_idle(specialist.id)

    async def generate_stream(
        self,
        question: str,
        specialist: Specialist,
        user_id: int,
        session_id: Optional[str] = None,
    ):
        """流式版 generate()：逐帧 yield delta，末尾 yield done。

        done 帧字段与 generate() 返回 dict 完全一致（多一个 "type"）。
        """
        request_id = str(uuid.uuid4())
        try:
            start_time = time.time()

            # ---- Step 1: 合规预检 ----
            registry.set_working(specialist.id, PHASE_COMPLIANCE_PRECHECK, question)
            logger.info(f"[{request_id}] 合规预检")
            question_check = await check_compliance(
                content=question,
                context={"user_id": user_id, "type": "user_input"}
            )
            if question_check.get("blocked"):
                yield {
                    "type": "done",
                    "answer": "您的问题包含不合规内容，请调整后重试。",
                    "citations": [],
                    "evidence_level": None,
                    "session_id": session_id,
                    "request_id": request_id,
                    "latency_ms": 0,
                    "blocked": True,
                    "violations": question_check.get("violations", []),
                }
                return

            # ---- Step 2: 百炼流式 ----
            logger.info(f"[{request_id}] 调用百炼 App: {specialist.bailian_app_id}")
            registry.set_working(specialist.id, PHASE_GENERATING, question)
            ai_prompt = question
            ai_response = None
            ai_model = "multimodal-dialog"
            answer = ""
            citations = []

            try:
                async for frame in self.bailian.chat_stream(
                    app_id=specialist.bailian_app_id,
                    prompt=question,
                    session_id=session_id,
                ):
                    if frame["type"] == "delta":
                        yield {"type": "delta", "text": frame["text"]}
                    elif frame["type"] == "done":
                        answer = frame.get("text", "")
                        citations = frame.get("citations", [])
                        session_id = frame.get("dialog_id", session_id)
                        ai_response = answer
                if not answer.strip():
                    raise BailianException("百炼返回空答案（App 未发布或无检索结果）")
            except BailianException as e:
                logger.warning(f"[{request_id}] 百炼调用失败，降级到通义千问: {e}")
                answer = self._fallback_generate(question, specialist)
                citations = []
                ai_response = answer
                ai_model = "qwen-max"
                yield {"type": "delta", "text": answer}

            # ---- Step 3: 合规审核 AI 答案 ----
            logger.info(f"[{request_id}] 合规审核答案")
            registry.set_working(specialist.id, PHASE_COMPLIANCE_REVIEW, question)
            answer_check = await check_compliance(
                content=answer,
                context={"user_id": user_id, "type": "ai_output", "specialist_id": specialist.id}
            )
            if answer_check.get("blocked"):
                latency_ms = int((time.time() - start_time) * 1000)
                from app.api.metrics import CHAT_LATENCY
                CHAT_LATENCY.observe(latency_ms / 1000.0)
                await write_audit_log(
                    user_id=user_id, action="chat_blocked", ai_involved=True,
                    ai_model=ai_model, ai_prompt=ai_prompt, ai_response=ai_response,
                    compliance_result=answer_check, request_id=request_id,
                )
                yield {
                    "type": "done",
                    "answer": "该问题建议直接咨询医学顾问。",
                    "citations": citations,
                    "evidence_level": None,
                    "session_id": session_id,
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                    "blocked": True,
                    "violations": answer_check.get("violations", []),
                }
                return

            # ---- Step 4: 审计日志 ----
            latency_ms = int((time.time() - start_time) * 1000)
            from app.api.metrics import CHAT_LATENCY
            CHAT_LATENCY.observe(latency_ms / 1000.0)
            await write_audit_log(
                user_id=user_id, action="chat_response",
                resource_type="conversation", ai_involved=True,
                ai_model=ai_model, ai_prompt=ai_prompt, ai_response=ai_response,
                compliance_result=answer_check, request_id=request_id,
            )
            logger.info(f"[{request_id}] 回答完成，耗时 {latency_ms}ms")

            yield {
                "type": "done",
                "answer": answer,
                "citations": citations,
                "evidence_level": self._extract_evidence_level(answer),
                "session_id": session_id,
                "request_id": request_id,
                "latency_ms": latency_ms,
                "blocked": False,
                "violations": [],
            }
        finally:
            registry.set_idle(specialist.id)

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
