"""陪练会话模型（需求 4.5 自动评分与进步曲线）+ 异议话术库（需求 3.2(5)）"""
from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class PracticeSession(Base, TimestampMixin):
    __tablename__ = "practice_sessions"

    representative_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    skill_id = Column(BigInteger, ForeignKey("skill_packages.id"))
    scenario = Column(String(100))
    status = Column(String(20), default="in_progress")
    scores = Column(JSONB)
    turn_count = Column(Integer, default=0)
    transcript = Column(JSONB)   # 三期 N：逐轮 Q&A [{turn, role(rep|ai), content}]

    def to_dict(self, include_transcript: bool = True) -> dict:
        d = {
            "id": self.id,
            "representative_id": self.representative_id,
            "skill_id": self.skill_id,
            "scenario": self.scenario,
            "status": self.status,
            "scores": self.scores,
            "turn_count": self.turn_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        # 2026-09-02 列表瘦身：GET /practices 分页不再携带全量 transcript
        # （历史列表只读 scenario/turn_count/scores；创建/收尾响应默认不变）
        if include_transcript:
            d["transcript"] = self.transcript
        return d


class ObjectionScript(Base, TimestampMixin):
    """异议话术库（需求 3.2(5)）：科室/性格/产品场景的医生异议话术，
    合规部审核（pending/approved/rejected）+ 版本留痕。"""

    __tablename__ = "objection_scripts"

    scenario_type = Column(String(50), nullable=False)
    objection_content = Column(Text, nullable=False)
    response_guidance = Column(Text)
    version = Column(String(20), default="1.0")
    review_status = Column(String(20), nullable=False, default="pending")
    review_reason = Column(String(500))
    reviewed_by = Column(BigInteger)
    created_by = Column(BigInteger)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scenario_type": self.scenario_type,
            "objection_content": self.objection_content,
            "response_guidance": self.response_guidance,
            "version": self.version,
            "review_status": self.review_status,
            "review_reason": self.review_reason,
            "reviewed_by": self.reviewed_by,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
