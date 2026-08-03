"""文档上传 -> 审核 -> 上线 流程管理"""
import logging
import os
import tempfile
from datetime import date
from typing import List, Optional, Tuple

from shared.common.response import BusinessError

from app.db.repositories.knowledge_repo import KnowledgeRepository
from app.services.bailian_knowledge_client import BailianKnowledgeClient, BailianKnowledgeError
from app.services.oss_client import OSSClient

logger = logging.getLogger(__name__)


class DocumentManager:
    def __init__(self, db):
        self.db = db
        self.repo = KnowledgeRepository(db)
        self.oss = OSSClient()
        self.bailian = BailianKnowledgeClient()

    def create_from_upload(
        self,
        local_path: str,
        title: str,
        doc_type: str,
        uploader_id: int,
        product_id: Optional[int] = None,
        evidence_level: Optional[str] = None,
        source: Optional[str] = None,
        publish_date: Optional[date] = None,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ):
        file_url = self.oss.upload_local_file(local_path)
        logger.info("document uploaded to OSS by user %s: %s", uploader_id, file_url)
        return self.repo.create_document(
            title=title,
            doc_type=doc_type,
            file_url=file_url,
            source=source,
            product_id=product_id,
            evidence_level=evidence_level,
            publish_date=publish_date,
            version=version,
            tags=tags,
            status="draft",
        )

    def approve_document(self, doc_id: int, reviewer_id: int):
        doc = self.repo.get(doc_id)
        if not doc:
            raise BusinessError("文档不存在", code=4001)
        if doc.status not in ("draft", "rejected"):
            raise BusinessError(f"当前状态 {doc.status} 不允许审核", code=4001)

        self.repo.update_status(doc_id, "processing", reviewer_id)
        try:
            if not doc.file_url:
                raise BailianKnowledgeError("document has no file_url")
            suffix = os.path.splitext(doc.file_url)[1]
            fd, local_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            try:
                self.oss.download_to_local(doc.file_url, local_path)
                self.bailian.import_document(
                    local_path=local_path,
                    original_file_url=doc.file_url,
                    tags=[doc.doc_type] if doc.doc_type else None,
                )
            finally:
                if os.path.exists(local_path):
                    os.unlink(local_path)
            logger.info("document %s imported to Bailian knowledge base", doc_id)
        except BailianKnowledgeError as exc:
            logger.exception("Bailian import failed for document %s", doc_id)
            self.repo.update_status(doc_id, "rejected", reviewer_id)
            raise BusinessError(str(exc), code=6000) from exc

        return self.repo.update_status(doc_id, "ready", reviewer_id)

    def reject_document(self, doc_id: int, reviewer_id: int):
        doc = self.repo.get(doc_id)
        if not doc:
            raise BusinessError("文档不存在", code=4001)
        return self.repo.update_status(doc_id, "rejected", reviewer_id)

    def search(
        self,
        query: str,
        product_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        top_k: int = 10,
    ) -> Tuple[List[dict], str]:
        try:
            results = self.bailian.search(
                query=query,
                top_k=top_k,
                product_id=product_id,
                doc_type=doc_type,
            )
            return results, "bailian"
        except Exception as exc:
            logger.warning("Bailian search failed, use local fallback: %s", exc)
            results = self.repo.local_search(
                query=query,
                product_id=product_id,
                doc_type=doc_type,
                top_k=top_k,
            )
            return results, "local_fallback"
