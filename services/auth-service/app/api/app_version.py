"""App 版本检查与更新提示（2026-09-15 挂账落地）

两端 App 启动时、以及从后台切回前台时静默查一次版本，据此决定是否提示更新：
    - 本机 < latest_version：弹「发现新版本」窗，用户可跳过
    - 本机 < min_version：强制更新（不更新不给用），故 min_version 别乱抬

端点：
    GET  /api/v1/app/version?platform=rep|doctor   公开（App 启动时可能尚未登录）
    GET  /api/v1/app/config                        管理端读（admin）：两端完整配置
    PUT  /api/v1/app/config/{platform}             管理端改（admin）：改版本号/下载地址/更新说明

为什么公开读：更新检查发生在登录之前（冷启动第一屏就是登录页），要 token 就没法查。

路径命名避坑：网关 PUBLIC_PATHS 是前缀匹配，公开路径叫 /version，管理端就叫 /config ——
若把管理端命名成 /versions，会因 "/api/v1/app/version" 是它的前缀而顺带被放开（鉴权失效）。
"""
import logging
import re
from typing import Optional, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.common.auth import require_roles
from shared.common.context import get_request_id
from shared.common.db_session import get_db
from shared.common.response import ParamError, success
from shared.models.app_version import AppVersion

from app.services.audit_client import write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/app", tags=["app-version"])

PLATFORMS = {"rep": "代表端", "doctor": "医生端"}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
MAX_NOTES_LEN = 2000


def parse_version(value: str) -> Tuple[int, int, int]:
    """'1.2.3' → (1,2,3)。调用前必须先过 VERSION_RE 校验。"""
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _default_row(platform: str) -> dict:
    """表里没有该平台的行时的兜底：等于「装着最新版」，不打扰用户。

    宁可漏提示不可误提示 —— 配置缺失时把用户挡在门外（弹强制更新）是最坏结果。
    """
    return {
        "platform": platform,
        "platform_label": PLATFORMS[platform],
        "latest_version": "1.0.0",
        "min_version": "1.0.0",
        "download_url": f"/apk/medagent-{platform}.apk",
        "release_notes": None,
        "updated_at": None,
    }


def _serialize(row: Optional[AppVersion], platform: str) -> dict:
    if row is None:
        return _default_row(platform)
    return {
        "platform": platform,
        "platform_label": PLATFORMS[platform],
        "latest_version": row.latest_version,
        "min_version": row.min_version,
        "download_url": row.download_url,
        "release_notes": row.release_notes,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _validate_version(value, field: str) -> str:
    text = (value or "").strip() if isinstance(value, str) else ""
    if not VERSION_RE.match(text):
        raise ParamError(f"{field} 格式应为 x.y.z（如 1.2.0）")
    return text


def _validate_download_url(value) -> str:
    text = (value or "").strip() if isinstance(value, str) else ""
    if not text:
        raise ParamError("下载地址不能为空")
    if len(text) > 500:
        raise ParamError("下载地址不能超过 500 字符")
    # 相对路径（App 侧补服务器地址）或绝对地址二选一
    if not (text.startswith("/") or text.startswith("http://") or text.startswith("https://")):
        raise ParamError("下载地址需以 / 开头（如 /apk/medagent-rep.apk）或以 http://、https:// 开头")
    return text


@router.get("/version")
async def get_app_version(platform: str, db: Session = Depends(get_db)):
    """App 端查询版本（公开，无需登录）。platform=rep（代表端）/ doctor（医生端）"""
    key = (platform or "").strip()
    if key not in PLATFORMS:
        raise ParamError("platform 必须是 rep（代表端）或 doctor（医生端）")
    row = db.query(AppVersion).filter(AppVersion.platform == key).first()
    return success(_serialize(row, key))


@router.get("/config")
async def list_app_versions(
    current_user: dict = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """管理端读两端完整配置（admin）—— web「系统配置 → App 版本与更新」用"""
    rows = {r.platform: r for r in db.query(AppVersion).all()}
    return success([_serialize(rows.get(p), p) for p in PLATFORMS])


@router.put("/config/{platform}")
async def update_app_version(
    platform: str,
    payload: dict,
    current_user: dict = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """管理端改某端版本配置（admin）。只传要改的字段，未传的保持原值"""
    key = (platform or "").strip()
    if key not in PLATFORMS:
        raise ParamError("platform 必须是 rep（代表端）或 doctor（医生端）")
    if not isinstance(payload, dict):
        raise ParamError("请求体必须是 JSON 对象")

    row = db.query(AppVersion).filter(AppVersion.platform == key).first()
    before = _serialize(row, key)

    latest = row.latest_version if row else None
    minimum = row.min_version if row else None
    download_url = row.download_url if row else None
    notes = row.release_notes if row else None

    touched = False
    if "latest_version" in payload:
        latest = _validate_version(payload["latest_version"], "最新版本号")
        touched = True
    if "min_version" in payload:
        minimum = _validate_version(payload["min_version"], "最低可用版本号")
        touched = True
    if "download_url" in payload:
        download_url = _validate_download_url(payload["download_url"])
        touched = True
    if "release_notes" in payload:
        raw = payload["release_notes"]
        if raw is None:
            notes = None
        else:
            if not isinstance(raw, str):
                raise ParamError("更新说明必须是文本")
            if len(raw) > MAX_NOTES_LEN:
                raise ParamError(f"更新说明不能超过 {MAX_NOTES_LEN} 字")
            notes = raw.strip() or None
        touched = True

    if not touched:
        raise ParamError("没有需要更新的字段")

    missing = [label for value, label in (
        (latest, "最新版本号"), (minimum, "最低可用版本号"), (download_url, "下载地址"),
    ) if not value]
    if missing:
        raise ParamError(f"首次配置必须提供：{'、'.join(missing)}")

    # 强制更新的门槛不能高于提示更新的门槛，否则「最低可用」比「最新」还新，逻辑自相矛盾
    if parse_version(minimum) > parse_version(latest):
        raise ParamError("最低可用版本号不能高于最新版本号")

    if row is None:
        row = AppVersion(platform=key)
        db.add(row)
    row.latest_version = latest
    row.min_version = minimum
    row.download_url = download_url
    row.release_notes = notes
    row.updated_by = current_user["id"]
    db.commit()
    db.refresh(row)

    after = _serialize(row, key)
    await write_audit_log(
        action="app_version_update",
        user_id=current_user["id"],
        resource_type="app_version",
        resource_id=key,
        before_value=before,
        after_value=after,
        request_id=get_request_id() or None,
    )
    return success(after)
