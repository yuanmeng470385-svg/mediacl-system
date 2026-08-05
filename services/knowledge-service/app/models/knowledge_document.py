"""知识库文档 ORM 模型"""
from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from shared.models.base import Base, TimestampMixin


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"

    title = Column(String(500), nullable=False)
    doc_type = Column(String(50), nullable=False)
    source = Column(String(200))
    content = Column(Text)
    file_url = Column(String(500))
    product_id = Column(BigInteger, ForeignKey("products.id"))
    evidence_level = Column(String(20))
    publish_date = Column(Date)
    version = Column(String(20))
    status = Column(String(20), default="draft")
    reviewer_id = Column(BigInteger, ForeignKey("users.id"))
    review_date = Column(DateTime)
    tags = Column(JSONB)
    revision = Column(Integer, default=1)              # 版本链计数（version 是用户可见文档版本字符串）
    parent_doc_id = Column(BigInteger, ForeignKey("knowledge_documents.id"))

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "doc_type": self.doc_type,
            "source": self.source,
            "content": self.content,
            "file_url": self.file_url,
            "product_id": self.product_id,
            "evidence_level": self.evidence_level,
            "publish_date": self.publish_date.isoformat() if self.publish_date else None,
            "version": self.version,
            "status": self.status,
            "reviewer_id": self.reviewer_id,
            "review_date": self.review_date.isoformat() if self.review_date else None,
            "tags": self.tags,
            "revision": self.revision,
            "parent_doc_id": self.parent_doc_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
