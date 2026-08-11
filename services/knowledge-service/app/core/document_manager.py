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
        # 版本管理：同 title+product 已有文档 → 新行 revision+1 挂 parent 链（M22）
        # 顺序保证：先 OSS 上传新文件 → 再建新文档行 → 最后归档旧版。
        # OSS 上传失败 → 直接抛错，旧版保持 ready 可检索；归档失败 → 记日志人工处理，旧版也不受影响。
        prev = self.repo.find_latest_by_title(self.db, title, product_id)
        revision = _next_revision(prev)
        parent_doc_id = prev.id if prev else None

        file_url = self.oss.upload_local_file(local_path)
        logger.info("document uploaded to OSS by user %s: %s", uploader_id, file_url)
        doc = self.repo.create_document(
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
        if prev:
            try:
                self.repo.archive(self.db, prev)
                # 合规硬伤回归：归档旧版必须同步清检索索引（DashVector/ES），
                # 否则新版本已上架、旧版仍能被向量/ES 检索命中（M23 只覆盖了
                # 驳回路径）。清理失败记日志但不回滚（旧版已归档，仅索引残留）。
                self._cleanup_indexes(prev.id, prev)
                logger.info("旧版文档 %s 已归档并清理检索索引（新版本 %s）", prev.id, doc.id)
            except Exception as exc:
                logger.error(
                    "归档旧版文档 %s 失败（新文档 %s 已入库，旧版仍为 ready，需人工处理）: %s",
                    prev.id, doc.id, exc,
                )
        return doc

    def approve_document(self, doc_id: int, reviewer_id: int):
        doc = self.repo.get(doc_id)
        if not doc:
            raise BusinessError("文档不存在", code=4001)
        if doc.status not in ("draft", "rejected"):
            raise BusinessError(f"当前状态 {doc.status} 不允许审核", code=4001)

        prev_status = doc.status  # M23：中途失败要恢复到的可重试状态
        # 并发防抖：先读后写存在竞态（两请求同时读到 draft 都进处理）。
        # 原子抢占（UPDATE 带状态条件）保证双击/多管理同时审核时只有一个成功。
        if not self.repo.try_mark_processing(doc_id, reviewer_id):
            raise BusinessError("文档正在审核中或状态已变化，请刷新后重试", code=4001)
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
                                # M27: product_id 元数据统一写 int，与 _filter_expr 的 int 字面量一致
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
            # 百炼导入失败：恢复为可重试状态（不卡死在 processing）
            logger.exception("Bailian import failed for document %s", doc_id)
            self._restore_status(doc_id, prev_status, reviewer_id)
            raise BusinessError(str(exc), code=6000) from exc
        except Exception as exc:
            # M23: OSS 下载失败 / httpx 错误等任意中途异常 → 状态恢复为可重试态，记录错误
            logger.exception("approve document %s failed, status restored to %s", doc_id, prev_status)
            self._restore_status(doc_id, prev_status, reviewer_id)
            raise BusinessError(f"审核处理失败（状态已恢复，可重试）: {exc}", code=5000) from exc

        # M21: ES 关键词索引（失败降级记日志，不阻塞审核）
        self._index_es(doc_id, doc.title or "", doc.content or "", doc)
        return self._finish_approve(doc_id, reviewer_id)

    def approve_without_bailian(self, doc_id: int, reviewer_id: int):
        """离线上架：仅本地正文入库 + 向量化，跳过百炼导入（种子/演示/无百炼凭证场景）"""
        from app.services.document_processor import extract_text, chunk_text
        doc = self.repo.get(doc_id)
        if not doc:
            raise BusinessError("文档不存在", code=4001)
        if doc.status not in ("draft", "rejected"):
            raise BusinessError(f"当前状态 {doc.status} 不允许审核", code=4001)
        if not doc.file_url:
            raise BusinessError("文档无 file_url", code=4001)
        prev_status = doc.status
        # H4：与 approve_document 同一把锁——原子抢占 processing，终态/恢复均带
        # 状态条件，否则并发驳回可被此路径（无百炼导入，耗时短但仍是竞态窗口）翻回
        if not self.repo.try_mark_processing(doc_id, reviewer_id):
            raise BusinessError("文档正在审核中或状态已变化，请刷新后重试", code=4001)
        import tempfile
        suffix = os.path.splitext(doc.file_url)[1]
        fd, local_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            self.oss.download_to_local(doc.file_url, local_path)
            text = extract_text(local_path)
        except Exception as exc:
            self._restore_status(doc_id, prev_status, reviewer_id)
            raise BusinessError(f"审核处理失败（状态已恢复，可重试）: {exc}", code=5000) from exc
        finally:
            if os.path.exists(local_path):
                os.unlink(local_path)
        if text:
            doc.content = text[:100000]
            if self.dashvector.is_configured():
                chunks = chunk_text(text)
                fields = {"doc_type": doc.doc_type or ""}
                if doc.product_id is not None:
                    # M27: product_id 元数据统一写 int，与 _filter_expr 的 int 字面量一致
                    fields["product_id"] = int(doc.product_id)
                try:
                    self.dashvector.upsert_chunks(
                        doc_id, doc.title or "", chunks,
                        fields=fields,
                    )
                    logger.info("document %s 向量化 %d chunks → DashVector", doc_id, len(chunks))
                except Exception as exc:
                    logger.error("DashVector 写入失败（不影响上架，检索将降级）: %s", exc)
        # M21: ES 关键词索引（失败降级记日志，不阻塞审核）
        self._index_es(doc_id, doc.title or "", doc.content or "", doc)
        return self._finish_approve(doc_id, reviewer_id)

    def _finish_approve(self, doc_id: int, reviewer_id: int):
        """终态写入（H4，2026-08-11）：仅 processing 可进入 ready。

        抢占 processing 后百炼导入可能长达 1h，期间被驳回/归档的文档不得被翻回
        ready（否则被驳回文档重新上架可检索）。条件更新失败说明状态已被他人改变
        ——不覆盖，如实报错让审核人员知晓。
        """
        if not self.repo.try_mark_final(doc_id, "ready", reviewer_id):
            raise BusinessError(
                "文档状态在审核期间被改变（可能已被驳回或归档），未上架。请刷新确认",
                code=4001,
            )
        return self.repo.get(doc_id)

    def _restore_status(self, doc_id: int, prev_status: str, reviewer_id: int) -> None:
        """失败恢复（H4，2026-08-11）：仅仍持有 processing 锁时回滚。

        审核中途失败恢复 prev_status 时若已被并发驳回/归档，不能把 rejected/
        archived 翻回 draft（否则被驳回文档绕过审核流程静默回到待审状态）。
        """
        if not self.repo.try_restore_status(doc_id, prev_status, reviewer_id):
            logger.warning(
                "文档 %s 状态在审核期间被改变（非 processing），未恢复为 %s（保持现状）",
                doc_id, prev_status,
            )

    def reject_document(self, doc_id: int, reviewer_id: int):
        doc = self.repo.get(doc_id)
        if not doc:
            raise BusinessError("文档不存在", code=4001)
        # M23: 状态校验。draft/processing 可驳回；ready 已上架 → 直接驳回并清理索引（响应会说明）；
        # 其他状态（archived 等）不允许驳回。
        if doc.status not in ("draft", "processing", "ready"):
            raise BusinessError(f"当前状态 {doc.status} 不允许驳回", code=4001)
        if doc.status == "ready":
            logger.warning("document %s 已上架（ready）被驳回，将同步清理检索索引", doc_id)
        # M23: 驳回时清理检索侧索引（DashVector 必删；ES 配置时删；百炼侧无删除封装则记日志说明）
        self._cleanup_indexes(doc_id, doc)
        return self.repo.update_status(doc_id, "rejected", reviewer_id)

    def _index_es(self, doc_id: int, title: str, content: str, doc) -> None:
        """M21: 上架后写入 ES 关键词索引；失败降级记日志，不阻塞审核流程"""
        if not content:
            return
        try:
            from app.services.es_client import EsClient
            es = EsClient()
            if not es.is_configured():
                return
            fields = {"doc_type": doc.doc_type or "", "status": "ready"}
            if doc.product_id is not None:
                fields["product_id"] = int(doc.product_id)
            ok = es.index_doc(doc_id, title, content, fields=fields)
            if ok:
                logger.info("document %s → ES index", doc_id)
        except Exception as exc:
            logger.warning("ES 索引写入失败（不影响审核）: %s", exc)

    def _cleanup_indexes(self, doc_id: int, doc) -> None:
        """M23: 驳回/下架时清理检索侧索引，避免被驳回文档仍可被检索"""
        # 1. DashVector：按 doc_id 删除全部 chunk（主向量后端，必删）
        if self.dashvector.is_configured():
            try:
                self.dashvector.delete_doc(doc_id)
                logger.info("document %s 已从 DashVector 删除", doc_id)
            except Exception as exc:
                logger.error("DashVector 删除失败（文档 %s 可能仍可被向量检索）: %s", doc_id, exc)
        # 2. ES：配置时同步删除
        try:
            from app.services.es_client import EsClient
            es = EsClient()
            if es.is_configured():
                es.delete_doc(doc_id)
        except Exception as exc:
            logger.error("ES 删除失败: %s", exc)
        # 3. 百炼侧：当前客户端未封装 DeleteFile 能力，若该文档此前已导入百炼，
        #    百炼知识库中文件仍在（仅作降级检索后端使用）；记录日志 + 注释限制。
        #    后续如需彻底清理：在 BailianKnowledgeClient 封装 DeleteFile API 后调用。
        if doc.status in ("ready", "processing") and doc.file_url:
            logger.warning(
                "document %s 驳回：百炼知识库文件无法经当前客户端删除"
                "（BailianKnowledgeClient 未封装 DeleteFile，见 M23 注释），需人工清理或等待降级链路覆盖",
                doc_id,
            )

    def search(
        self,
        query: str,
        product_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        top_k: int = 10,
    ) -> Tuple[List[dict], str]:
        # M21: ES 配置时优先关键词检索（未配置走原 PG/DashVector 路径）
        try:
            from app.services.es_client import EsClient
            es = EsClient()
            if es.is_configured():
                results = es.search(query, top_k=top_k, product_id=product_id, doc_type=doc_type)
                return results, "es"
        except Exception as exc:
            logger.warning("ES 检索失败，继续走向量/降级路径: %s", exc)
        # 1. DashVector（向量 + 关键词混合，可选后端）
        if self.dashvector.is_configured():
            try:
                results = self._hybrid_search(query, product_id, doc_type, top_k)
                return results, "dashvector"
            except Exception as exc:
                logger.warning("DashVector 检索失败，降级百炼: %s", exc)
        # 2. 百炼（dense + rerank）—— M27: 百炼不支持 product_id/doc_type 过滤，
        #    降级到此时明确打 warning 提示过滤被丢弃，不静默
        if product_id is not None or doc_type:
            logger.warning(
                "Bailian 检索不支持 product_id/doc_type 过滤，过滤条件将被丢弃"
                "（product_id=%s, doc_type=%s）",
                product_id, doc_type,
            )
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
            # M27: doc_type 值转义（去掉引号），避免注入使 DashVector 表达式出错。
            # 注意：DashVector filter 字符串字面量用双引号（单引号查询恒不命中）。
            safe = str(doc_type).replace('"', "").replace("'", "")
            parts.append(f'doc_type = "{safe}"')
        return " AND ".join(parts) if parts else None
