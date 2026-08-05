"""DashVector 向量检索客户端（方案 9.1/9.2：向量化 + 向量检索）

未配置 DASHVECTOR_API_KEY/ENDPOINT 时 is_configured()=False，调用方降级到百炼/本地。
"""
import os
import logging
from typing import Dict, List, Optional

import dashscope
from http import HTTPStatus

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # text-embedding-v3


def _embed(text: str) -> List[float]:
    """向量化（text-embedding-v3，1536 维）"""
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "")
    resp = dashscope.TextEmbedding.call(
        model=os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3"),
        input=text[:2048],
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
            client.create(self.collection_name, dimension=EMBEDDING_DIM)
            logger.info("DashVector collection 已创建: %s", self.collection_name)
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
        col.upsert(docs)
        return len(docs)

    def query(self, vector: List[float], filter_expr: Optional[str] = None, top_k: int = 10) -> List[Dict]:
        """向量检索（含过滤）"""
        col = self._get_collection()
        resp = col.query(
            vector=vector,
            topk=top_k,
            filter=filter_expr,
            output_fields=["doc_id", "title", "content", "chunk_index", "product_id", "doc_type"],
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
            })
        return out
