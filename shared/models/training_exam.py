"""培训考试模型（需求文档 3.4/附录A training_materials/exam_questions/exam_records）"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class TrainingMaterial(Base, TimestampMixin):
    __tablename__ = "training_materials"

    title = Column(String(200), nullable=False)
    material_type = Column(String(20), nullable=False)   # regulation / rdpac / internal
    content = Column(Text, nullable=False)
    version = Column(String(20), default="1.0")
    status = Column(String(20), default="active")        # active / archived
    created_by = Column(BigInteger, ForeignKey("users.id"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "material_type": self.material_type,
            "content": self.content,
            "version": self.version,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ExamQuestion(Base, TimestampMixin):
    __tablename__ = "exam_questions"

    material_id = Column(BigInteger, ForeignKey("training_materials.id"))
    question_type = Column(String(10), nullable=False)   # single / multiple / judge
    content = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False)
    answer = Column(JSONB, nullable=False)
    review_status = Column(String(20), default="pending")  # pending / approved / rejected
    review_reason = Column(String(500))
    reviewed_by = Column(BigInteger)
    reviewed_at = Column(DateTime)
    created_by = Column(BigInteger, ForeignKey("users.id"))

    def to_dict(self, expose_answer: bool = False) -> dict:
        d = {
            "id": self.id,
            "material_id": self.material_id,
            "question_type": self.question_type,
            "content": self.content,
            "options": self.options,
            "review_status": self.review_status,
            "review_reason": self.review_reason,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if expose_answer:
            d["answer"] = self.answer
        return d


class ExamRecord(Base, TimestampMixin):
    __tablename__ = "exam_records"

    representative_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    question_count = Column(Integer, nullable=False)
    correct_count = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "representative_id": self.representative_id,
            "question_count": self.question_count,
            "correct_count": self.correct_count,
            "score": self.score,
            "passed": self.passed,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
        }
