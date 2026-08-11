"""医生数据访问层 — CRUD、搜索、标签、批量导入"""
import logging
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.hcp import Hcp

logger = logging.getLogger(__name__)

# 可写字段白名单（防 mass assignment）：id/created_at/updated_at 由系统管理，
# 白名单外的 key 一律剔除。create/update/batch_create 共用兜底过滤；
# API 层另有严格校验（白名单外字段直接 400，见 hcps.py _validate_hcp_fields）。
HCP_WRITABLE_FIELDS = {
    "name", "hospital", "department", "title", "specialty", "phone", "email",
    "region", "academic_background", "prescription_preference",
    "influence_level", "tags", "status",
}


def _filter_writable(data: Dict) -> Dict:
    """白名单过滤：系统字段（id/created_at/updated_at）与未知 key 一律剔除"""
    return {k: v for k, v in (data or {}).items() if k in HCP_WRITABLE_FIELDS}


def _to_tags(tags: Any) -> List[str]:
    """把 tags 统一成字符串列表（兼容 list / 逗号分隔字符串 / None）"""
    if isinstance(tags, list):
        return [str(t).strip() for t in tags if str(t).strip()]
    if isinstance(tags, str) and tags.strip():
        return [t.strip() for t in tags.split(",") if t.strip()]
    return []


def _merge_profile_fields(base: dict, updates: dict) -> dict:
    """画像 JSONB 合并：新 key 写入，已有 key 不覆盖（保留人工/历史数据）；tags 去重追加"""
    result = dict(base)
    for key, value in (updates or {}).items():
        if value is None:
            continue
        if key == "tags":
            existing = result.get("tags") or []
            merged_tags = list(existing)
            for tag in value:
                if tag not in merged_tags:
                    merged_tags.append(tag)
            result["tags"] = merged_tags
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            merged = dict(result[key])
            for k, v in value.items():
                if k not in merged:
                    merged[k] = v
            result[key] = merged
        elif key not in result or result[key] is None:
            result[key] = value
    return result


class HcpRepo:
    """医生档案仓库"""

    @staticmethod
    def get(db: Session, hcp_id: int) -> Optional[Hcp]:
        return db.query(Hcp).filter(Hcp.id == hcp_id).first()

    @staticmethod
    def list(db: Session, page: int = 1, page_size: int = 20, **filters) -> Tuple[List[Hcp], int]:
        """分页列表 + 筛选（name/hospital/department/title/region/status/tag）"""
        query = db.query(Hcp)

        name = filters.get("name")
        if name:
            query = query.filter(Hcp.name.ilike(f"%{name}%"))
        hospital = filters.get("hospital")
        if hospital:
            query = query.filter(Hcp.hospital.ilike(f"%{hospital}%"))
        department = filters.get("department")
        if department:
            query = query.filter(Hcp.department.ilike(f"%{department}%"))
        title = filters.get("title")
        if title:
            query = query.filter(Hcp.title.ilike(f"%{title}%"))
        region = filters.get("region")
        if region:
            query = query.filter(Hcp.region == region)
        status = filters.get("status")
        if status:
            query = query.filter(Hcp.status == status)
        tag = filters.get("tag")
        if tag:
            # JSONB 数组包含判断：tags @> [tag]
            from sqlalchemy.dialects.postgresql import JSONB
            query = query.filter(Hcp.tags.cast(JSONB).contains([tag]))

        total = query.count()
        items = query.order_by(Hcp.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    @staticmethod
    def create(db: Session, data: Dict) -> Hcp:
        """创建医生档案（仅接受白名单字段，系统字段/未知 key 忽略）"""
        data = _filter_writable(data)
        data["tags"] = _to_tags(data.get("tags"))
        hcp = Hcp(**data)
        db.add(hcp)
        db.commit()
        db.refresh(hcp)
        logger.info(f"创建医生档案: {hcp.name} (id={hcp.id})")
        return hcp

    @staticmethod
    def update(db: Session, hcp: Hcp, data: Dict) -> Hcp:
        """更新医生档案（仅更新白名单内传入字段）"""
        for key, value in _filter_writable(data).items():
            if key == "tags":
                value = _to_tags(value)
            if value is not None:
                setattr(hcp, key, value)
        db.commit()
        db.refresh(hcp)
        return hcp

    @staticmethod
    def batch_create(db: Session, rows: List[Dict]) -> Tuple[int, List[Dict]]:
        """批量导入：逐行创建，单行失败不阻塞其余行

        Returns:
            (成功数, [{"row": N, "error": "..."}, ...])
        """
        imported = 0
        errors = []
        for idx, row in enumerate(rows, start=1):
            try:
                HcpRepo.create(db, row)
                imported += 1
            except Exception as e:
                logger.warning(f"批量导入第 {idx} 行失败: {e}")
                errors.append({"row": idx, "error": str(e)})
        return imported, errors

    @staticmethod
    def add_tags(db: Session, hcp: Hcp, tags: List[str]) -> Hcp:
        """添加标签（去重，保留原标签）"""
        current = set(_to_tags(hcp.tags))
        current.update(_to_tags(tags))
        hcp.tags = sorted(current)
        db.commit()
        db.refresh(hcp)
        return hcp

    @staticmethod
    def remove_tags(db: Session, hcp: Hcp, tags: List[str]) -> Hcp:
        """删除标签（忽略不存在的标签）"""
        current = set(_to_tags(hcp.tags))
        for t in _to_tags(tags):
            current.discard(t)
        hcp.tags = sorted(current)
        db.commit()
        db.refresh(hcp)
        return hcp

    @staticmethod
    def merge_profile(db: Session, hcp, updates: dict):
        """按合并语义更新画像字段（academic_background/prescription_preference/influence_level/tags）"""
        profile_keys = ("academic_background", "prescription_preference", "influence_level", "tags")
        current = {k: getattr(hcp, k) for k in profile_keys}
        merged = _merge_profile_fields(current, updates)
        for k in profile_keys:
            setattr(hcp, k, merged.get(k))
        db.commit()
        db.refresh(hcp)
        return hcp
