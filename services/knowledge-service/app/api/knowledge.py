"""知识库服务 API 路由"""
import json
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from shared.common.auth import get_current_user
from shared.common.db_session import get_db
from shared.common.pagination import paginate
from shared.common.response import BusinessError, ParamError, success

from app.core.document_manager import DocumentManager

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)

ALLOWED_DOC_TYPES = ("product", "guideline", "literature", "regulation", "competitor", "other")


def _manager(db: Session) -> DocumentManager:
    return DocumentManager(db)


@router.post("/search")
async def search_knowledge(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (request.get("query") or "").strip()
    if not query:
        raise ParamError("query 不能为空")
    results, source = _manager(db).search(
        query=query,
        product_id=request.get("product_id"),
        doc_type=request.get("doc_type"),
        top_k=int(request.get("top_k", 10)),
    )
    return success({"results": results, "source": source})


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: str = Form(...),
    product_id: Optional[int] = Form(None),
    evidence_level: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    publish_date: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not title.strip():
        raise ParamError("title 不能为空")
    if doc_type not in ALLOWED_DOC_TYPES:
        raise ParamError("doc_type 不合法")

    parsed_tags = None
    if tags:
        try:
            parsed_tags = json.loads(tags)
        except json.JSONDecodeError as exc:
            raise ParamError("tags 必须是 JSON 数组") from exc

    parsed_date = None
    if publish_date:
        try:
            parsed_date = date.fromisoformat(publish_date)
        except ValueError as exc:
            raise ParamError("publish_date 格式应为 YYYY-MM-DD") from exc

    suffix = Path(file.filename or "").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        tmp.write(file.file.read())

    try:
        doc = _manager(db).create_from_upload(
            local_path=tmp_path,
            title=title,
            doc_type=doc_type,
            uploader_id=current_user["id"],
            product_id=product_id,
            evidence_level=evidence_level,
            source=source,
            publish_date=parsed_date,
            version=version,
            tags=parsed_tags,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return success(doc.to_dict())


@router.get("/documents")
async def list_documents(
    status: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = _manager(db).repo.list_documents(
        status=status,
        doc_type=doc_type,
        product_id=product_id,
        page=page,
        page_size=page_size,
    )
    return success(paginate([d.to_dict() for d in items], total=total, page=page, page_size=page_size))


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _manager(db).repo.get(doc_id)
    if not doc:
        raise BusinessError("文档不存在", code=4001)
    return success(doc.to_dict())


@router.post("/documents/{doc_id}/review")
async def review_document(
    doc_id: int,
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    manager = _manager(db)
    if request.get("approved"):
        doc = manager.approve_document(doc_id, current_user["id"])
    else:
        doc = manager.reject_document(doc_id, current_user["id"])
    return success(doc.to_dict())


@router.post("/feedback")
async def submit_feedback(
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    logger.info("knowledge feedback from user %s: %s", current_user["id"], request)
    return success({"received": True})


@router.get("/stats")
async def knowledge_stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func as sqlfunc

    from app.models.knowledge_document import KnowledgeDocument

    total = db.query(sqlfunc.count(KnowledgeDocument.id)).scalar() or 0
    status_rows = (
        db.query(KnowledgeDocument.status, sqlfunc.count(KnowledgeDocument.id))
        .group_by(KnowledgeDocument.status)
        .all()
    )
    manager = _manager(db)
    return success(
        {
            "total": total,
            "by_status": {status: count for status, count in status_rows},
            "workspace_id": manager.bailian.workspace_id,
            "knowledge_base_id": manager.bailian.kb_id,
            "app_id": manager.bailian.app_id,
        }
    )
