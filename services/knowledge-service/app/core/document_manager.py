"""文档上传 -> 审核 -> 上线 流程管理"""
import logging
import os
import tempfile
from datetime import date
from typing import List, Optional, Tuple

from shared.common.response import BusinessError

from app.db.repositories.knowledge_repo import KnowledgeRepository
from app.services.bailian_knowledge_client import BailianKnowledgeClient, BailianKnowledgeError
from app.services.dashvector_client import DashVectorClient
from app.services.oss_client import OSSClient

logger = logging.getLogger(__name__)


def _next_revision(prev) -> int:
    return (prev.revision if prev else 0) + 1


class DocumentManager:
    def __init__(self, db):
        self.db = db
        self.repo = KnowledgeRepository(db)
        self.oss = OSSClient()
        self.bailian = BailianKnowledgeClient()
        self.dashvector = DashVectorClient()

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
        # 版本管理：同 title+product 已有文档 → 旧版归档，新行 revision+1 挂 parent 链
        prev = self.repo.find_latest_by_title(self.db, title, product_id)
        parent_doc_id = None
        revision = 1
        if prev:
            revision = _next_revision(prev)
            parent_doc_id = prev.id
            try:
                self.repo.archive(self.db, prev)
            except Exception as exc:
                logger.warning("归档旧版文档失败（不影响新文档）: %s", exc)

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
            revision=revision,
            parent_doc_id=parent_doc_id,
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
                # 正文入库 + DashVector 向量化（可选后端：未配置自动跳过）
                from app.services.document_processor import extract_text, chunk_text
                text = extract_text(local_path)
                if text:
                    doc.content = text[:100000]  # 截断防超长
                    chunks = chunk_text(text)
                    if self.dashvector.is_configured():
                        try:
                            fields = {"doc_type": doc.doc_type or ""}
                            if doc.product_id is not None:
                                fields["product_id"] = int(doc.product_id)
                            self.dashvector.upsert_chunks(
                                doc_id, doc.title or "", chunks,
                                fields=fields,
                            )
                            logger.info("document %s 向量化 %d chunks → DashVector", doc_id, len(chunks))
                        except Exception as exc:
                            logger.error("DashVector 写入失败（不影响上架，检索将降级）: %s", exc)
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
        # 1. DashVector（向量 + 关键词混合，可选后端）
        if self.dashvector.is_configured():
            try:
                results = self._hybrid_search(query, product_id, doc_type, top_k)
                return results, "dashvector"
            except Exception as exc:
                logger.warning("DashVector 检索失败，降级百炼: %s", exc)
        # 2. 百炼（dense + rerank）
        try:
            results = self.bailian.search(query=query, top_k=top_k, product_id=product_id, doc_type=doc_type)
            return results, "bailian"
        except Exception as exc:
            logger.warning("Bailian search failed, use local fallback: %s", exc)
        # 3. 本地 SQL（关键词）
        results = self.repo.local_search(query=query, product_id=product_id, doc_type=doc_type, top_k=top_k)
        return results, "local_fallback"

    def _hybrid_search(self, query, product_id, doc_type, top_k):
        """DashVector 向量 + 本地关键词 加权融合（0.7 向量 / 0.3 关键词）"""
        from app.services.dashvector_client import _embed
        vector_results = self.dashvector.query(_embed(query), self._filter_expr(product_id, doc_type), top_k=top_k * 2)
        keyword_results = self.repo.local_search(query=query, product_id=product_id, doc_type=doc_type, top_k=top_k * 2)

        # 向量分归一化到 [0,1]（DashVector score 通常 <1）
        vec_max = max((r["score"] for r in vector_results), default=0.0) or 1.0
        kw_max = max((r["score"] for r in keyword_results), default=0.0) or 1.0

        merged = {}
        for r in vector_results:
            key = str(r["doc_id"])  # doc_id 统一为 str，避免与 local 的 int 键错位导致加权失效
            merged[key] = {"title": r["title"], "content": r["content"],
                           "doc_id": key, "score": 0.7 * r["score"] / vec_max,
                           "backend": "dashvector"}
        for r in keyword_results:
            key = str(r["doc_id"])
            if key in merged:
                merged[key]["score"] += 0.3 * r["score"] / kw_max
            else:
                merged[key] = {"title": r["title"], "content": r["content"],
                               "doc_id": r["doc_id"], "score": 0.3 * r["score"] / kw_max,
                               "backend": "local"}
        ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _filter_expr(product_id, doc_type) -> Optional[str]:
        parts = []
        if product_id:
            parts.append(f"product_id = {int(product_id)}")
        if doc_type:
            parts.append(f"doc_type = '{doc_type}'")
        return " AND ".join(parts) if parts else None
