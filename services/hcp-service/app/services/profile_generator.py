"""医生画像生成器 — 聚合基础档案 + 互动历史，经通义千问生成 AI 画像

未配置 DASHSCOPE_API_KEY 或 LLM 调用失败时降级为基础数据聚合，不阻塞业务。
"""
import json
import logging
from typing import Dict, List, Optional

from app.services.qwen_client import QwenClient
from app.models.hcp import Hcp
from app.db.repositories.visit_interaction_repo import list_interactions
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_PROFILE_PROMPT = """你是医药行业客户关系管理专家。请根据以下医生档案和最近互动记录，生成该医生的客户画像。

医生档案：
{profile}

最近互动记录：
{interactions}

请严格输出 JSON（不要 markdown 代码块），包含以下字段：
1. academic_profile — 学术画像（1-2 句话，基于学术背景、职称、影响力）
2. prescription_preference — 处方偏好分析（1-2 句话，基于处方偏好与互动中的兴趣点）
3. communication_advice — 拜访沟通建议（2-3 条，基于互动中的异议与关注点）
4. next_step_suggestion — 下一步跟进建议（1-2 句话）
5. risk_alert — 合规风险提示（如互动中有违规倾向记录，给出提示；无则写"无"）
"""


class ProfileGenerator:
    """医生画像生成器"""

    def __init__(self, qwen: QwenClient = None):
        self.qwen = qwen or QwenClient()

    def generate(self, db: Session, hcp: Hcp, interaction_limit: int = 5,
                 user_id: Optional[int] = None) -> Dict:
        """生成画像

        Args:
            user_id: 查看者用户 id（H3，2026-08-11）——非空时互动历史只聚合该代表
                本人的记录（防跨用户泄漏，与 /interactions 的 rep 过滤语义一致）；
                None 表示聚合全部（仅 admin/manager 调用方使用）。

        Returns:
            {"ai_profile": {...}, "interactions": [...], "degraded": false}
            或 {"ai_profile": {"summary": "..."}, "interactions": [...], "degraded": true, "reason": "..."}
        """
        interactions = list_interactions(db, hcp.id, limit=interaction_limit, user_id=user_id)
        base_profile = hcp.to_dict()

        try:
            prompt = _PROFILE_PROMPT.format(
                profile=json.dumps(base_profile, ensure_ascii=False, indent=2),
                interactions=json.dumps(interactions, ensure_ascii=False, indent=2),
            )
            resp = self.qwen.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=800,
            )
            content = resp["content"].strip()
            # 兼容模型输出 ```json ... ``` 包裹
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:]
            ai_profile = json.loads(content)
            return {"ai_profile": ai_profile, "interactions": interactions, "degraded": False}
        except Exception as e:
            logger.warning(f"AI 画像生成失败，降级为基础数据聚合: {e}")
            return {
                "ai_profile": {
                    "summary": "AI 画像暂不可用（未配置 DASHSCOPE_API_KEY 或 LLM 调用失败）",
                    "base_info": {
                        "title": base_profile.get("title"),
                        "specialty": base_profile.get("specialty"),
                        "hospital": base_profile.get("hospital"),
                        "influence_level": base_profile.get("influence_level"),
                        "tags": base_profile.get("tags"),
                    },
                },
                "interactions": interactions,
                "degraded": True,
                "reason": str(e)[:200],
            }
