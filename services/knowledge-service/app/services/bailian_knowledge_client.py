"""Bailian knowledge base client (Alibaba Cloud SDK).

Upload flow:
  1. ApplyFileUploadLease -> pre-signed URL + lease id
  2. HTTP PUT the file to the pre-signed URL
  3. AddFile -> file id, parsing starts automatically
  4. DescribeFile -> poll until status == PARSE_SUCCESS
  5. SubmitIndexAddDocumentsJob -> append file ids to the knowledge base
  6. GetIndexJobStatus -> poll until status == COMPLETED
"""
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from alibabacloud_bailian20231229 import models as bailian_models
from alibabacloud_bailian20231229.client import Client as BailianClient
from alibabacloud_tea_openapi import models as open_api_models

from app.config import settings

logger = logging.getLogger(__name__)

BAILIAN_ENDPOINT = "bailian.cn-beijing.aliyuncs.com"
PARSER = "DASHSCOPE_DOCMIND"
CATEGORY_ID = "default"
CATEGORY_TYPE = "UNSTRUCTURED"
SOURCE_TYPE = "DATA_CENTER_FILE"


class BailianKnowledgeError(Exception):
    pass


def _retry(fn, retries: int = 5, base_delay: float = 5.0):
    last_error = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - transient TLS/proxy failures
            last_error = exc
            logger.warning(
                "Bailian call attempt %s/%s failed: %s",
                attempt + 1,
                retries,
                exc,
            )
            if attempt < retries - 1:
                time.sleep(base_delay * (attempt + 1))
    raise last_error


class BailianKnowledgeClient:
    def __init__(self):
        # Local dev proxy (e.g. 127.0.0.1:7897) breaks TLS to Aliyun API hosts.
        current_no_proxy = os.environ.get("NO_PROXY", "") or os.environ.get("no_proxy", "")
        if "aliyuncs.com" not in current_no_proxy:
            extra = ",.aliyuncs.com" if current_no_proxy else ".aliyuncs.com"
            os.environ["NO_PROXY"] = current_no_proxy + extra
            os.environ["no_proxy"] = current_no_proxy + extra

        self.workspace_id = settings.BAILIAN_WORKSPACE_ID
        self.kb_id = settings.BAILIAN_KB_ID
        self.index_id = settings.BAILIAN_INDEX_ID or settings.BAILIAN_KB_ID
        self.app_id = settings.BAILIAN_APP_ID
        self.client = BailianClient(
            open_api_models.Config(
                access_key_id=settings.ALIBABA_CLOUD_ACCESS_KEY_ID,
                access_key_secret=settings.ALIBABA_CLOUD_ACCESS_KEY_SECRET,
                endpoint=BAILIAN_ENDPOINT,
            )
        )
        self.file_poll_interval = 10
        self.file_poll_timeout = 60 * 60
        self.job_poll_interval = 10
        self.job_poll_timeout = 60 * 60

    @staticmethod
    def _md5(file_path: str) -> str:
        digest = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _check_success(self, response: Any, action: str):
        body = getattr(response, "body", None)
        success = getattr(body, "success", None)
        code = getattr(body, "code", None)
        ok_codes = (None, "", "0", "200", "Success", "success")
        if success in (False, "false", "False") or (code not in ok_codes):
            message = getattr(body, "message", "unknown")
            raise BailianKnowledgeError(f"{action} failed: code={code} message={message}")
        return body

    def apply_file_upload_lease(self, file_path: str) -> Dict[str, Any]:
        file_name = Path(file_path).name
        if len(file_name) < 4:
            raise BailianKnowledgeError("file name must be at least 4 characters")
        request = bailian_models.ApplyFileUploadLeaseRequest(
            category_type=CATEGORY_TYPE,
            file_name=file_name,
            md_5=self._md5(file_path),
            size_in_bytes=str(os.path.getsize(file_path)),
        )
        response = self.client.apply_file_upload_lease(
            CATEGORY_ID,
            self.workspace_id,
            request,
        )
        body = self._check_success(response, "ApplyFileUploadLease")
        data = body.data
        return {
            "lease_id": data.file_upload_lease_id,
            "url": data.param.url,
            "method": data.param.method,
            "headers": data.param.headers,
        }

    def _upload_to_lease_url(self, file_path: str, lease: Dict[str, Any]) -> None:
        headers = {str(k): str(v) for k, v in (lease.get("headers") or {}).items()}
        method = lease.get("method") or "PUT"
        url = lease["url"]
        with open(file_path, "rb") as f:
            response = httpx.request(
                method,
                url,
                headers=headers,
                content=f.read(),
                timeout=120,
            )
        response.raise_for_status()

    def add_file(
        self,
        lease_id: str,
        original_file_url: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        request = bailian_models.AddFileRequest(
            category_id=CATEGORY_ID,
            category_type=CATEGORY_TYPE,
            lease_id=lease_id,
            original_file_url=original_file_url,
            parser=PARSER,
            tags=tags,
        )
        response = self.client.add_file(self.workspace_id, request)
        body = self._check_success(response, "AddFile")
        return body.data.file_id

    def describe_file(self, file_id: str):
        request = bailian_models.DescribeFileRequest()
        response = self.client.describe_file(self.workspace_id, file_id, request)
        body = self._check_success(response, "DescribeFile")
        return body.data

    def wait_for_parse(self, file_id: str, timeout: Optional[int] = None):
        deadline = time.time() + (timeout or self.file_poll_timeout)
        while time.time() < deadline:
            data = self.describe_file(file_id)
            status = data.status
            logger.info("file %s parse status: %s", file_id, status)
            if status == "PARSE_SUCCESS":
                return data
            if status == "PARSE_FAILED":
                raise BailianKnowledgeError(
                    f"file parse failed: {data.parse_error_message}"
                )
            time.sleep(self.file_poll_interval)
        raise BailianKnowledgeError("file parse timeout")

    def submit_index_add_documents_job(self, file_ids: List[str]) -> str:
        request = bailian_models.SubmitIndexAddDocumentsJobRequest(
            document_ids=file_ids,
            index_id=self.index_id,
            source_type=SOURCE_TYPE,
        )
        response = _retry(
            lambda: self.client.submit_index_add_documents_job(
                self.workspace_id,
                request,
            )
        )
        body = self._check_success(response, "SubmitIndexAddDocumentsJob")
        if body.data is None:
            logger.error("submit index job response: %s", body.to_map())
            raise BailianKnowledgeError(
                f"SubmitIndexAddDocumentsJob returned no data: "
                f"code={body.code} message={body.message} status={body.status}"
            )
        return body.data.id

    def get_index_job_status(self, job_id: str):
        request = bailian_models.GetIndexJobStatusRequest(
            index_id=self.index_id,
            job_id=job_id,
            page_number=1,
            page_size=10,
        )
        response = _retry(
            lambda: self.client.get_index_job_status(self.workspace_id, request)
        )
        body = self._check_success(response, "GetIndexJobStatus")
        return body.data

    def list_indices(self, page_number: int = 1, page_size: int = 20):
        request = bailian_models.ListIndicesRequest(
            page_number=str(page_number),
            page_size=str(page_size),
        )
        response = _retry(
            lambda: self.client.list_indices(self.workspace_id, request)
        )
        body = self._check_success(response, "ListIndices")
        return body.data

    def wait_for_index_job(self, job_id: str, timeout: Optional[int] = None):
        deadline = time.time() + (timeout or self.job_poll_timeout)
        while time.time() < deadline:
            data = self.get_index_job_status(job_id)
            status = data.status
            logger.info("index job %s status: %s", job_id, status)
            if status == "COMPLETED":
                return data
            if status == "FAILED":
                raise BailianKnowledgeError(f"index job failed: {job_id}")
            time.sleep(self.job_poll_interval)
        raise BailianKnowledgeError("index job timeout")

    def import_document(
        self,
        local_path: str,
        original_file_url: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        lease = self.apply_file_upload_lease(local_path)
        self._upload_to_lease_url(local_path, lease)
        file_id = self.add_file(
            lease["lease_id"],
            original_file_url=original_file_url,
            tags=tags,
        )
        self.wait_for_parse(file_id)
        job_id = self.submit_index_add_documents_job([file_id])
        self.wait_for_index_job(job_id)
        return {"file_id": file_id, "job_id": job_id}

    def retrieve(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        request = bailian_models.RetrieveRequest(
            index_id=self.index_id,
            query=query,
            dense_similarity_top_k=top_k,
            sparse_similarity_top_k=0,
            enable_reranking=True,
            rerank_top_n=top_k,
        )
        response = _retry(
            lambda: self.client.retrieve(self.workspace_id, request)
        )
        body = self._check_success(response, "Retrieve")
        results = []
        for node in body.data.nodes or []:
            metadata = node.metadata or {}
            results.append(
                {
                    "title": metadata.get("file_name", ""),
                    "content": node.text or "",
                    "score": node.score,
                    "doc_id": metadata.get("file_id", ""),
                }
            )
        return results

    def search(
        self,
        query: str,
        top_k: int = 10,
        product_id: Optional[int] = None,
        doc_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Bailian retrieval does not support product_id/doc_type filters.
        return self.retrieve(query, top_k=top_k)
