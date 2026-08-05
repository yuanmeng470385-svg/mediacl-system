"""Elasticsearch 可选客户端 —— ES_URL 配置时启用，未配置自动降级（PG FTS 承担关键词索引）"""
import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class EsClient:
    def __init__(self):
        self.url = os.getenv("ES_URL", "")
        self.index = os.getenv("ES_INDEX", "knowledge_documents")

    def is_configured(self) -> bool:
        return bool(self.url)

    def client(self):
        from elasticsearch import Elasticsearch
        return Elasticsearch(self.url)

    def index_doc(self, doc_id: int, title: str, content: str, fields: Optional[Dict] = None):
        if not self.is_configured():
            return False
        try:
            es = self.client()
            es.index(index=self.index, id=f"doc_{doc_id}", document={
                "title": title, "content": content, "doc_id": doc_id, **(fields or {}),
            })
            return True
        except Exception as exc:
            logger.warning("ES 写入失败（降级）: %s", exc)
            return False

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        if not self.is_configured():
            return []
        es = self.client()
        resp = es.search(index=self.index, size=top_k, query={
            "multi_match": {"query": query, "fields": ["title^3", "content"]},
        })
        return [
            {"title": h["_source"].get("title", ""), "content": (h["_source"].get("content") or "")[:500],
             "score": h.get("_score", 0), "doc_id": h["_source"].get("doc_id")}
            for h in resp["hits"]["hits"]
        ]
