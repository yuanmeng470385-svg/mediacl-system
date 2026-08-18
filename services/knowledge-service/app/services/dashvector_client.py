"""DashVector 向量检索客户端（方案 9.1/9.2：向量化 + 向量检索）

未配置 DASHVECTOR_API_KEY/ENDPOINT 时 is_configured()=False，调用方降级到百炼/本地。
"""
import os
import logging
from typing import Dict, List, Optional

import dashscope
from http import HTTPStatus

logger = logging.getLogger(__name__)

# text-embedding-v3 最大输出 1024 维（dimensions 参数只支持向下收缩，不能扩到
# 1536）。此前误设为 1536 → collection 以 1536 维创建 → 每次 upsert 维度不匹配
# 静默失败 → 向量检索从未真正生效（合规硬伤：检索一直降级走百炼/本地）。
EMBEDDING_DIM = 1024  # text-embedding-v3


def _embed(text: str) -> List[float]:
    """向量化（text-embedding-v3，1024 维；dimensions 显式指定防默认行为漂移）"""
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")
    resp = dashscope.TextEmbedding.call(
        model=os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3"),
        input=text[:2048],
        dimensions=EMBEDDING_DIM,
    )
    if resp.status_code == HTTPStatus.OK:
        return resp.output["embeddings"][0]["embedding"]
    raise RuntimeError(f"向量化失败: {resp}")


class DashVectorClient:
    def __init__(self):
        self.api_key = os.getenv("DASHVECTOR_API_KEY", "")
        self.endpoint = os.getenv("DASHVECTOR_ENDPOINT", "")
        self.collection_name = os.getenv("DASHVECTOR_COLLECTION", "knowledge_base")
        self._collection = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.endpoint)

    def _get_collection(self):
        """获取（不存在则创建）collection —— 懒加载 + 缓存"""
        if self._collection is not None:
            return self._collection
        import dashvector as dv  # 运行期导入 + 属性查找，便于测试 monkeypatch dashvector.Client
        client = dv.Client(api_key=self.api_key, endpoint=self.endpoint)
        try:
            resp = client.create(self.collection_name, dimension=EMBEDDING_DIM)
            # create 对已存在的 collection 返回 code=-2025 错误响应但不抛异常，
            # 不能据此误报"已创建"
            if getattr(resp, "code", 0) == 0:
                logger.info("DashVector collection 已创建: %s", self.collection_name)
            else:
                logger.debug("collection 已存在或创建失败（走 get）: %s", getattr(resp, "message", ""))
        except Exception as exc:
            logger.debug("collection 已存在或创建失败（走 get）: %s", exc)
        self._collection = client.get(self.collection_name)
        if self._collection is None:
            raise RuntimeError(f"DashVector collection 不可用: {self.collection_name}")
        return self._collection

    def upsert_chunks(self, doc_id: int, title: str, chunks: List[str], fields: Optional[Dict] = None) -> int:
        """按 chunk 写入向量 + 元数据字段"""
        from dashvector import Doc
        col = self._get_collection()
        docs = []
        for i, chunk in enumerate(chunks):
            docs.append(Doc(
                id=f"doc_{doc_id}_chunk_{i}",
                vector=_embed(chunk),
                fields={
                    "doc_id": str(doc_id),
                    "title": title,
                    "chunk_index": i,
                    "content": chunk,
                    **(fields or {}),
                },
            ))
        resp = col.upsert(docs)
        # 响应式 API：失败返回错误码但不抛异常。必须检查，否则"上架成功但
        # 向量缺失"会静默发生（1536/1024 维度不匹配事件即如此）。
        code = getattr(resp, "code", None)
        if code not in (0, None):
            raise RuntimeError(
                f"DashVector upsert 失败: code={code} {getattr(resp, 'message', '')}"
            )
        return len(docs)

    def delete_doc(self, doc_id: int) -> bool:
        """按 doc_id 删除该文档的全部 chunk（驳回/下架时清理检索索引，M23）

        注意：dashvector SDK 1.0.23 的 Collection.delete 只接受 ids / delete_all，
        不接受 filter 表达式（旧写法 col.delete(filter=...) 会抛 TypeError，导致
        归档/驳回时向量索引实际未清理 —— 合规硬伤）。这里先按 doc_id filter
        查回该文档全部 chunk id，再按 ids 删除。向量用零向量即可（filter 精确
        匹配 doc_id，向量值不影响召回）。
        """
        col = self._get_collection()
        doc_id_str = str(int(doc_id))
        resp = col.query(
            vector=[0.0] * EMBEDDING_DIM,
            # DashVector filter 字符串字面量必须用双引号（单引号查不到）
            filter=f'doc_id = "{doc_id_str}"',
            topk=1000,
            output_fields=["doc_id"],
        )
        ids = [item.id for item in (resp.output or [])]
        if not ids:
            logger.info("document %s 在 DashVector 无残留 chunk", doc_id)
            return True
        col.delete(ids=ids)
        logger.info("document %s 已从 DashVector 删除 %d chunks", doc_id, len(ids))
        return True

    def query(self, vector: List[float], filter_expr: Optional[str] = None, top_k: int = 10) -> List[Dict]:
        """向量检索（含过滤）"""
        col = self._get_collection()
        resp = col.query(
            vector=vector,
            topk=top_k,
            filter=filter_expr,
            output_fields=["doc_id", "title", "content", "chunk_index", "product_id", "doc_type", "file_url"],
        )
        # C4（2026-08-13 低危批）：响应式 API —— 查询失败返回错误码但不抛异常，
        # resp.output 为空列表会被当作"无结果"正常返回，document_manager.search
        # 的降级链（DashVector → 百炼 → 本地）永远不会触发。与 upsert 同款检查：
        # code 非 0/None 即失败，必须 raise 让上层降级。
        code = getattr(resp, "code", None)
        if code not in (0, None):
            raise RuntimeError(
                f"DashVector query 失败: code={code} {getattr(resp, 'message', '')}"
            )
        out = []
        for item in resp.output or []:
            fields = item.fields or {}
            out.append({
                "id": item.id,
                "score": getattr(item, "score", 0),
                "doc_id": fields.get("doc_id"),
                "title": fields.get("title"),
                "content": fields.get("content", "")[:500],
                "chunk_index": fields.get("chunk_index"),
                "product_id": fields.get("product_id"),
                "doc_type": fields.get("doc_type"),
                "url": fields.get("file_url") or "",
            })
        return out
