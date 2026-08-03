"""百炼知识库管理客户端

REST 接口走 BAILIAN_API_BASE；对话类 WebSocket 由 A 的 specialist-service 使用。
如果团队百炼控制台的接口路径与本文件不同，只需调整 _url() 或顶部常量。
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class BailianKnowledgeError(Exception):
    pass


class BailianKnowledgeClient:
    def __init__(self):
        self.base_url = settings.BAILIAN_API_BASE.rstrip("/")
        self.api_key = settings.BAILIAN_API_KEY
        self.workspace_id = settings.BAILIAN_WORKSPACE_ID
        self.kb_id = settings.BAILIAN_KB_ID
        self.app_id = settings.BAILIAN_APP_ID
        self.timeout = 30

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return (
            f"{self.base_url}/workspace/{self.workspace_id}"
            f"/knowledge-base/{self.kb_id}{path}"
        )

    def _request(self, method: str, path: str, payload: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            response = httpx.request(
                method,
                self._url(path),
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and data.get("code") not in (None, 0, 200):
                raise BailianKnowledgeError(str(data))
            return data
        except httpx.HTTPError as exc:
            logger.error("Bailian knowledge API error: %s", exc)
            raise BailianKnowledgeError(f"百炼知识库接口调用失败: {exc}") from exc

    def import_document(
        self,
        file_url: str,
        title: str,
        doc_type: str,
        evidence_level: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "fileUrl": file_url,
            "title": title,
            "docType": doc_type,
            "evidenceLevel": evidence_level,
            "source": source,
        }
        return self._request("POST", "/document/import", payload)

    def list_documents(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        return self._request("GET", f"/documents?page={page}&pageSize={page_size}")

    def enable_document(self, document_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/documents/{document_id}/enable", {})

    def delete_document(self, document_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/documents/{document_id}")

    def search(
        self,
        query: str,
        top_k: int = 10,
        product_id: Optional[int] = None,
        doc_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        payload = {
            "query": query,
            "topK": top_k,
            "productId": product_id,
            "docType": doc_type,
        }
        data = self._request("POST", "/search", payload)
        docs = data.get("documents") or data.get("results") or data.get("data") or []
        results = []
        for doc in docs:
            results.append(
                {
                    "title": doc.get("title", ""),
                    "content": doc.get("content", doc.get("text", "")),
                    "evidence_level": doc.get("evidence_level"),
                    "score": doc.get("score", 0.0),
                    "doc_id": doc.get("documentId", doc.get("id")),
                }
            )
        return results
