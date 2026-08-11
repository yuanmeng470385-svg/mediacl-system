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

from shared.common.auth import get_current_user, require_roles
from app.models.knowledge_feedback import KnowledgeFeedback
from app.services.audit_client import write_audit_log

# 知识库管理端点（S6 RBAC / S9）：上传与审核限 admin/manager/medical（方案要求医学顾问审核）
KB_ADMIN_ROLES = ("admin", "manager", "medical")
from shared.common.db_session import get_db
from shared.common.pagination import paginate
from shared.common.response import BusinessError, ParamError, success

from app.core.document_manager import DocumentManager

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)

ALLOWED_DOC_TYPES = ("product", "guideline", "literature", "regulation", "competitor", "other")

# M24: 上传校验 —— 扩展名白名单（旧格式 .doc/.ppt 明确排除）+ 大小上限 50MB
ALLOWED_FILE_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt"}
LEGACY_BLOCKED_EXTENSIONS = {".doc", ".ppt"}
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
_UPLOAD_READ_CHUNK = 1024 * 1024  # 1MB 分块读取，避免全量读内存


def _parse_bool_value(value, name: str = "approved") -> bool:
    """M24: 显式布尔解析 —— 字符串 "false"/"0" 必须解析为 False"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "y", "on"):
            return True
        if v in ("false", "0", "no", "n", "off"):
            return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    raise ParamError(f"{name} 必须是布尔值（true/false）")


def _can_view_all_documents(user: dict) -> bool:
    """M26: 仅审核角色（admin/manager/medical）可见未上架文档"""
    return (user.get("role") or "") in KB_ADMIN_ROLES


def _manager(db: Session) -> DocumentManager:
    return DocumentManager(db)


def validate_search_request(request: dict) -> dict:
    query = (request.get("query") or "").strip()
    if not query:
        raise ParamError("query 不能为空")
    try:
        top_k = int(request.get("top_k", 10))
    except (TypeError, ValueError):
        raise ParamError("top_k 必须是整数")
    if top_k < 1 or top_k > 50:
        raise ParamError("top_k 必须在 1-50 之间")
    return {"query": query, "top_k": top_k}


@router.post("/search")
async def search_knowledge(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = validate_search_request(request)
    results, source = _manager(db).search(
        query=data["query"],
        product_id=request.get("product_id"),
        doc_type=request.get("doc_type"),
        top_k=data["top_k"],
    )
    return success({"results": results, "source": source,
                    "empty": not results and source != "bailian",
                    "message": "知识库暂无已上架文档，请先上传并审核文档" if not results and source != "bailian" else None})


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
    current_user: dict = Depends(require_roles(*KB_ADMIN_ROLES)),
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

    suffix = (Path(file.filename or "").suffix or "").lower()
    # M24: 扩展名白名单；旧格式 .doc/.ppt 明确拒绝并提示转换
    if suffix in LEGACY_BLOCKED_EXTENSIONS:
        raise ParamError(f"不支持旧版格式 {suffix}，请转换为 .docx/.pptx 后上传")
    if suffix not in ALLOWED_FILE_EXTENSIONS:
        raise ParamError(
            f"不支持的文件类型 {suffix or '(无扩展名)'}，仅支持: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}"
        )
    # M24: 分块落盘 + 大小上限（50MB），超过直接拒绝，不把大文件读进内存
    total_read = 0
    over_limit = False
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        while True:
            chunk = file.file.read(_UPLOAD_READ_CHUNK)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > MAX_UPLOAD_SIZE:
                over_limit = True
                break
            tmp.write(chunk)
    if over_limit:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise ParamError(f"文件大小超过上限 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB，拒绝上传")

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

    await write_audit_log(
        user_id=current_user["id"], action="doc_upload",
        resource_type="knowledge_document", resource_id=str(doc.id),
        after_value={"title": doc.title, "doc_type": doc.doc_type, "status": doc.status},
    )
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
    # M26: 非审核角色（如 rep）只能看到已上架（ready）文档，忽略其传入的 status 过滤
    if not _can_view_all_documents(current_user):
        status = "ready"
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
    # M26: 未上架文档（draft/rejected/archived）对非审核角色不可见（rep 看不到全文）
    if doc.status != "ready" and not _can_view_all_documents(current_user):
        raise BusinessError("文档不存在或无权访问", code=4001)
    return success(doc.to_dict())


@router.post("/documents/{doc_id}/review")
async def review_document(
    doc_id: int,
    request: dict,
    current_user: dict = Depends(require_roles(*KB_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    manager = _manager(db)
    # 契约：{"approved": true/false}。兼容旧前端传 {"action": "approve"|"reject"}
    approved_raw = request.get("approved")
    if approved_raw is None:
        approved = request.get("action") == "approve"
    else:
        # M24: 显式布尔解析，字符串 "false" 必须解析为 False（原 bool("false") == True 是 bug）
        approved = _parse_bool_value(approved_raw)
    if approved:
        doc = manager.approve_document(doc_id, current_user["id"])
    else:
        doc = manager.reject_document(doc_id, current_user["id"])
        # M23: 驳回时说明索引已清理；已上架文档被驳回时响应 message 提示
        if doc.status == "rejected":
            return success(doc.to_dict(), message="文档已驳回，检索索引已同步清理")
    await write_audit_log(
        user_id=current_user["id"], action="doc_review",
        resource_type="knowledge_document", resource_id=str(doc_id),
        after_value={"approved": approved, "status": doc.status},
    )
    return success(doc.to_dict())


@router.post("/search-test")
async def search_test(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """检索测试：同一 query 并行调多个后端对比（各自独立容错）"""
    import time
    data = validate_search_request(request)
    backends = request.get("backends") or ["dashvector", "bailian", "local"]
    manager = _manager(db)
    from app.services.dashvector_client import DashVectorClient
    from app.services.es_client import EsClient

    def _run(backend: str) -> dict:
        start = time.time()
        try:
            if backend == "dashvector":
                if not manager.dashvector.is_configured():
                    return {"backend": "dashvector", "error": "DashVector 未配置", "results": []}
                results = manager._hybrid_search(data["query"], request.get("product_id"), request.get("doc_type"), data["top_k"])
                return {"backend": "dashvector", "results": results, "elapsed_ms": int((time.time() - start) * 1000)}
            if backend == "bailian":
                results = manager.bailian.search(query=data["query"], top_k=data["top_k"])
                return {"backend": "bailian", "results": results, "elapsed_ms": int((time.time() - start) * 1000)}
            if backend == "local":
                results = manager.repo.local_search(query=data["query"], top_k=data["top_k"])
                return {"backend": "local", "results": results, "elapsed_ms": int((time.time() - start) * 1000)}
            if backend == "es":
                es = EsClient()
                if not es.is_configured():
                    return {"backend": "es", "error": "ES 未配置（ES_URL）", "results": []}
                return {"backend": "es", "results": es.search(data["query"], data["top_k"], product_id=request.get("product_id"), doc_type=request.get("doc_type")), "elapsed_ms": int((time.time() - start) * 1000)}
            return {"backend": backend, "error": f"未知后端 {backend}", "results": []}
        except Exception as exc:
            logger.error("search-test 后端 %s 失败: %s", backend, exc)
            return {"backend": backend, "error": str(exc), "results": []}

    outputs = [_run(b) for b in backends]
    return success({"query": data["query"], "backends": outputs})


def validate_feedback_request(request: dict) -> dict:
    query = (request.get("query") or "").strip()
    if not query:
        raise ParamError("query 不能为空")
    rating = request.get("rating")
    if rating not in (1, -1):
        raise ParamError("rating 必须是 1（有用）或 -1（无用）")
    return {"query": query, "rating": rating,
            # doc_id 兼容 int/str（历史客户端传数字 id），强转 str 防 500
            "doc_id": str(request.get("doc_id") or "")[:100],
            "comment": (request.get("comment") or "")[:500]}


@router.post("/feedback")
async def submit_feedback(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """反馈检索质量（真实落库）"""
    data = validate_feedback_request(request)
    fb = KnowledgeFeedback(
        user_id=current_user["id"], query=data["query"],
        doc_id=data["doc_id"], rating=data["rating"], comment=data["comment"],
    )
    db.add(fb)
    db.commit()
    await write_audit_log(
        user_id=current_user["id"], action="knowledge_feedback",
        resource_type="knowledge_document", resource_id=data["doc_id"],
        after_value=data,
    )
    return success({"feedback_id": fb.id}, "反馈已记录")


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
