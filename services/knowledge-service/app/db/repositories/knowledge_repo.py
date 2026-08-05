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
        revision: int = 1,
        parent_doc_id: Optional[int] = None,
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
            revision=revision,
            parent_doc_id=parent_doc_id,
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

    @staticmethod
    def find_latest_by_title(db: Session, title: str, product_id: Optional[int]) -> Optional[KnowledgeDocument]:
        q = db.query(KnowledgeDocument).filter(KnowledgeDocument.title == title)
        if product_id is not None:
            q = q.filter(KnowledgeDocument.product_id == product_id)
        return q.order_by(KnowledgeDocument.revision.desc()).first()

    @staticmethod
    def archive(db: Session, doc: KnowledgeDocument) -> KnowledgeDocument:
        doc.status = "archived"
        db.commit()
        db.refresh(doc)
        return doc

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

    def local_search(self, query, product_id=None, doc_type=None, top_k=10):
        """本地关键词检索（PostgreSQL 全文检索：标题+正文 tsvector，ts_rank 排序）"""
        from sqlalchemy import func
        q = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.status == "ready")
        if product_id:
            q = q.filter(KnowledgeDocument.product_id == product_id)
        if doc_type:
            q = q.filter(KnowledgeDocument.doc_type == doc_type)

        ts_expr = func.to_tsvector(
            "simple",
            func.coalesce(KnowledgeDocument.title, "") + " " + func.coalesce(KnowledgeDocument.content, ""),
        )
        ts_query = func.plainto_tsquery("simple", query)
        keyword = f"%{query}%"
        q = q.filter(
            or_(
                KnowledgeDocument.title.ilike(keyword),
                KnowledgeDocument.content.ilike(keyword),
                ts_expr.op("@@")(ts_query),
            )
        )
        docs = q.order_by(func.ts_rank(ts_expr, ts_query).desc()).limit(top_k).all()
        results = []
        for doc in docs:
            content = doc.content or ""
            title = doc.title or ""
            score = 1.0 if (query.lower() in title.lower() or (doc.content and query in doc.content)) else 0.7
            results.append({
                "title": title,
                "content": content[:500],
                "evidence_level": doc.evidence_level,
                "score": score,
                "doc_id": doc.id,
            })
        return results
