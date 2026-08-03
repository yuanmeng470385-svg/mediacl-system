"""知识库文档数据访问层"""
from datetime import date, datetime
from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_document(
        self,
        title: str,
        doc_type: str,
        file_url: str,
        source: Optional[str] = None,
        content: Optional[str] = None,
        product_id: Optional[int] = None,
        evidence_level: Optional[str] = None,
        publish_date: Optional[date] = None,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: str = "draft",
    ) -> KnowledgeDocument:
        doc = KnowledgeDocument(
            title=title,
            doc_type=doc_type,
            source=source,
            content=content,
            file_url=file_url,
            product_id=product_id,
            evidence_level=evidence_level,
            publish_date=publish_date,
            version=version,
            tags=tags,
            status=status,
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get(self, doc_id: int) -> Optional[KnowledgeDocument]:
        return self.db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()

    def list_documents(
        self,
        status: Optional[str] = None,
        doc_type: Optional[str] = None,
        product_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[KnowledgeDocument], int]:
        query = self.db.query(KnowledgeDocument)
        if status:
            query = query.filter(KnowledgeDocument.status == status)
        if doc_type:
            query = query.filter(KnowledgeDocument.doc_type == doc_type)
        if product_id:
            query = query.filter(KnowledgeDocument.product_id == product_id)
        total = query.count()
        items = (
            query.order_by(KnowledgeDocument.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    def update_status(
        self,
        doc_id: int,
        status: str,
        reviewer_id: Optional[int] = None,
    ) -> Optional[KnowledgeDocument]:
        doc = self.get(doc_id)
        if not doc:
            return None
        doc.status = status
        if reviewer_id is not None:
            doc.reviewer_id = reviewer_id
        if status in ("ready", "rejected", "processing"):
            doc.review_date = datetime.utcnow()
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def local_search(
        self,
        query: str,
        product_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        top_k: int = 10,
    ) -> List[dict]:
        q = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.status == "ready")
        if product_id:
            q = q.filter(KnowledgeDocument.product_id == product_id)
        if doc_type:
            q = q.filter(KnowledgeDocument.doc_type == doc_type)
        keyword = f"%{query}%"
        q = q.filter(
            or_(
                KnowledgeDocument.title.ilike(keyword),
                KnowledgeDocument.content.ilike(keyword),
            )
        )
        docs = q.limit(top_k).all()
        results = []
        for doc in docs:
            content = doc.content or ""
            title = doc.title or ""
            score = 0.9 if query.lower() in title.lower() else 0.6
            results.append(
                {
                    "title": title,
                    "content": content[:500],
                    "evidence_level": doc.evidence_level,
                    "score": score,
                    "doc_id": doc.id,
                }
            )
        return results
