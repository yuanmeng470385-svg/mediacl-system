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
import asyncio
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
        db=None,
    ) -> Dict:
        """
        生成回答（主流程）

        Args:
            question: 用户问题
            specialist: 数字专员 ORM 对象（含 bailian_app_id）
            user_id: 当前用户 ID
            session_id: 会话 ID（多轮对话时传入上次返回的 dialog_id）
            db: DB 会话（D5 起降级多轮上下文需要；未传则不拼历史，兼容旧调用/单测）

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
                # D3（2026-08-13）：预检被拦留痕 —— 与答案被拦路径同口径：
                # 观测延迟 + 写 question_blocked 审计（此前被拦请求在审计
                # 与监控中完全不可见）
                latency_ms = int((time.time() - start_time) * 1000)
                from app.api.metrics import CHAT_LATENCY
                CHAT_LATENCY.observe(latency_ms / 1000.0)
                await write_audit_log(
                    user_id=user_id,
                    action="question_blocked",
                    ai_involved=False,
                    ai_prompt=question,
                    compliance_result=question_check,
                    request_id=request_id,
                )
                return {
                    "answer": "您的问题包含不合规内容，请调整后重试。",
                    "citations": [],
                    "evidence_level": None,
                    "session_id": session_id,
                    "request_id": request_id,
                    "latency_ms": latency_ms,
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
                # G3（2026-08-13）：qwen 是同步 SDK 调用，放入 worker 线程，
                # 避免阻塞事件循环拖垮同进程其他请求
                # D5（2026-08-13）：降级带多轮上下文 —— 同 session 最近几轮
                # 问答拼入 qwen messages，追问不再丢上下文
                history = self._load_fallback_history(db, session_id, user_id)
                answer = await asyncio.to_thread(
                    self._fallback_generate, question, specialist, history,
                )
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
        db=None,
    ):
        """流式版 generate()：逐帧 yield delta，末尾 yield done。

        done 帧字段与 generate() 返回 dict 完全一致（多一个 "type"）。
        流式合规门禁：Step 2 每帧对累积文本做关键词/正则快速检查（fast），
        命中 reject 立即阻断 —— 不再等流结束才事后检查（旧实现违规文本已逐帧
        发给客户端）。阻断时产出 compliance 帧（客户端可据此提示）+ 掩码 done。
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
                # D3（2026-08-13）：预检被拦留痕 —— 与 REST generate 同口径：
                # 观测延迟 + 写 question_blocked 审计（此前被拦请求在审计
                # 与监控中完全不可见）
                latency_ms = int((time.time() - start_time) * 1000)
                from app.api.metrics import CHAT_LATENCY
                CHAT_LATENCY.observe(latency_ms / 1000.0)
                await write_audit_log(
                    user_id=user_id,
                    action="question_blocked",
                    ai_involved=False,
                    ai_prompt=question,
                    compliance_result=question_check,
                    request_id=request_id,
                )
                yield {
                    "type": "done",
                    "answer": "您的问题包含不合规内容，请调整后重试。",
                    "citations": [],
                    "evidence_level": None,
                    "session_id": session_id,
                    "request_id": request_id,
                    "latency_ms": latency_ms,
                    "blocked": True,
                    "violations": question_check.get("violations", []),
                }
                return

            # ---- Step 2: 百炼流式（逐帧合规门禁） ----
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
                        # 流式合规门禁（S-*）：对累积文本做关键词/正则快速检查
                        # （fast=True 跳语义层，毫秒级），命中 reject 立即阻断，
                        # 当前 delta 不转发 —— 违规内容不再到达客户端。
                        # G1（2026-08-13）：百炼 RespondingContent.text 每帧是全量
                        # 累积文本（非增量，见 bailian_client"每次是全量"），直接取
                        # 帧文本即可；旧实现 answer + text 拼接会产出"你你好…"
                        # 重复前缀 —— 误拦截风险 + ai_response/compliance_blocks
                        # 审计留痕损坏 + O(n²) 膨胀。answer 仅作最终落库/审计用。
                        accumulated = frame["text"]
                        frame_check = await check_compliance(
                            content=accumulated,
                            context={"user_id": user_id, "type": "ai_output", "specialist_id": specialist.id},
                            fast=True,
                        )
                        if frame_check.get("blocked"):
                            answer = accumulated
                            ai_response = answer
                            logger.info(f"[{request_id}] 流式门禁命中，阻断输出（违规帧不转发）")
                            async for blocked in self._blocked_frames(
                                answer, user_id, specialist, session_id,
                                request_id, start_time, ai_model, ai_prompt, citations,
                            ):
                                yield blocked
                            return
                        answer = accumulated
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
                # G3（2026-08-13）：qwen 是同步 SDK 调用，放入 worker 线程，
                # 避免阻塞事件循环（与 REST generate 同一口径）
                # D5（2026-08-13）：降级带多轮上下文（与 REST generate 同口径）
                history = self._load_fallback_history(db, session_id, user_id)
                answer = await asyncio.to_thread(
                    self._fallback_generate, question, specialist, history,
                )
                citations = []
                ai_response = answer
                ai_model = "qwen-max"
                # 降级是整段一次性输出，同样先过门禁（否则 Step 3 事后检查前
                # 客户端已看到全文，与旧实现同样的合规旁路）
                frame_check = await check_compliance(
                    content=answer,
                    context={"user_id": user_id, "type": "ai_output", "specialist_id": specialist.id},
                    fast=True,
                )
                if frame_check.get("blocked"):
                    logger.info(f"[{request_id}] 降级输出命中合规门禁，阻断输出")
                    async for blocked in self._blocked_frames(
                        answer, user_id, specialist, session_id,
                        request_id, start_time, ai_model, ai_prompt, citations,
                    ):
                        yield blocked
                    return
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

    async def _blocked_frames(
        self,
        text: str,
        user_id: int,
        specialist: Specialist,
        session_id: Optional[str],
        request_id: str,
        start_time: float,
        ai_model: str,
        ai_prompt: str,
        citations: list,
    ):
        """流式门禁命中后的阻断帧序列。

        对已生成文本做一次全量复核（fast=False，含语义层 + 拦截记录入库 +
        拦截指标），写 chat_blocked 审计，然后产出：
          1. {"type": "compliance", "blocked": True, "violations": [...]} —— 门禁信号
          2. {"type": "done", ..., "blocked": True} —— 掩码 done：客户端以此收尾
             （RN 端 done.blocked 会清掉已渲染的增量文本并展示合规提示）
        """
        full_check = await check_compliance(
            content=text,
            context={"user_id": user_id, "type": "ai_output", "specialist_id": specialist.id},
        )
        latency_ms = int((time.time() - start_time) * 1000)
        from app.api.metrics import CHAT_LATENCY, COMPLIANCE_BLOCKS
        CHAT_LATENCY.observe(latency_ms / 1000.0)
        # D1（2026-08-13）：COMPLIANCE_BLOCKS 接线（此前死代码恒 0 —— arms 告警
        # 引用的 compliance_blocks_total 在 specialist 侧无样本）。口径对齐
        # compliance checker：只计 action=reject；blocked=True 但 violations
        # 缺 action 字段（旧版检查结果/测试替身）时兜底按 reject 记一条。
        violations = full_check.get("violations", []) or []
        rejects = [v for v in violations if (v or {}).get("action") == "reject"]
        for v in (rejects or [{}]):
            COMPLIANCE_BLOCKS.labels(
                action="reject", severity=(v or {}).get("severity", "unknown"),
            ).inc()
        await write_audit_log(
            user_id=user_id, action="chat_blocked", ai_involved=True,
            ai_model=ai_model, ai_prompt=ai_prompt, ai_response=text,
            compliance_result=full_check, request_id=request_id,
        )
        yield {
            "type": "compliance",
            "blocked": True,
            "violations": full_check.get("violations", []),
        }
        yield {
            "type": "done",
            "answer": "该问题建议直接咨询医学顾问。",
            "citations": citations,
            "evidence_level": None,
            "session_id": session_id,
            "request_id": request_id,
            "latency_ms": latency_ms,
            "blocked": True,
            "violations": full_check.get("violations", []),
        }

    # ==================== 降级方案 ====================

    def _fallback_generate(
        self,
        question: str,
        specialist: Specialist,
        history: Optional[list] = None,
    ) -> str:
        """百炼不可用时，直接调通义千问（不带知识库检索）。

        同步函数（qwen SDK 阻塞式）：调用方必须用 asyncio.to_thread 包裹，
        本函数内部已兜底 —— 降级也失败时返回固定话术而非抛异常。

        D5（2026-08-13）：
        - history：同 session 最近几轮问答 [{"role": "user"/"assistant",
          "content": ...}]，拼在最终 prompt 之前，让追问有上下文；
        - 输出硬性 300 字符截断（提示词"不超过 300 字"对模型只是软约束），
          max_tokens 同步收紧（中文约 1-2 token/字，600 封顶防超长后再截）。
        """
        prompt = f"""你是{specialist.name}，医药产品 AI 学术专员。

代表问题：{question}

要求：
1. 简洁回答，不超过 300 字
2. 不确定时建议咨询医学顾问
3. 严禁承诺疗效、提及回扣、讨论医生处方量

回答："""

        messages = []
        for m in (history or []):
            role = m.get("role") if isinstance(m, dict) else None
            content = m.get("content") if isinstance(m, dict) else None
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        try:
            result = self.qwen.chat(
                messages=messages,
                model="qwen-max",
                temperature=0.1,
                max_tokens=600,
            )
            content = (result.get("content") or "")
            if len(content) > 300:
                logger.info(
                    f"降级回答 {len(content)} 字符超 300 字上限，截断为 300"
                )
                content = content[:300]
            return content
        except Exception as e:
            logger.error(f"降级生成也失败: {e}")
            return "抱歉，服务暂时不可用，请稍后重试或直接咨询医学顾问。"

    def _load_fallback_history(self, db, session_id: Optional[str], user_id: int) -> list:
        """降级多轮上下文：取同 session 最近几轮问答（最多 3 轮 / 6 行）。

        D5（2026-08-13）：此前降级每次都只有当前问题，追问丢上下文。
        归属校验复用 assert_session_owner（防经 generate 直调时跨用户读历史；
        端点层已校验过，这里是纵深防御）。db 未传 / 无 session_id 时返回空列表。
        """
        if db is None or not session_id:
            return []
        from app.models.conversation import Conversation
        from app.api.conversations import assert_session_owner
        assert_session_owner(db, session_id, user_id)
        rows = db.query(Conversation).filter(
            Conversation.session_id == session_id,
            Conversation.user_id == user_id,
        ).order_by(Conversation.id.desc()).limit(6).all()
        history = [
            {"role": "user" if r.role == "user" else "assistant", "content": r.content}
            for r in reversed(rows)
        ]
        return history

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
