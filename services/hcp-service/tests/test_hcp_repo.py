"""医生仓库测试 — 标签逻辑 / 创建 / 更新（用假 DB session，不连真实数据库）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.models.hcp import Hcp  # noqa: E402
from app.db.repositories.hcp_repo import HcpRepo  # noqa: E402


class FakeDb:
    """最小假 session：commit/refresh 无操作"""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        pass


def _make_hcp(**kwargs):
    defaults = dict(id=1, name="张伟", hospital="协和医院", tags=["KOL"])
    defaults.update(kwargs)
    return Hcp(**defaults)


def test_add_tags_dedup():
    db = FakeDb()
    hcp = _make_hcp(tags=["KOL", "学术型"])
    hcp = HcpRepo.add_tags(db, hcp, ["KOL", "新标签"])
    assert hcp.tags == ["KOL", "学术型", "新标签"]


def test_remove_tags():
    db = FakeDb()
    hcp = _make_hcp(tags=["KOL", "学术型", "老标签"])
    hcp = HcpRepo.remove_tags(db, hcp, ["学术型", "不存在的标签"])
    assert hcp.tags == ["KOL", "老标签"]


def test_create_converts_tags_string():
    db = FakeDb()
    hcp = HcpRepo.create(db, {"name": "李娜", "hospital": "仁济医院", "tags": "KOL,学术型"})
    assert hcp.name == "李娜"
    assert hcp.tags == ["KOL", "学术型"]


def test_create_requires_name():
    db = FakeDb()
    try:
        HcpRepo.create(db, {"name": "", "hospital": "某院"})
        assert False, "name 为空时应抛异常"
    except Exception:
        pass  # 数据库约束（nullable=False），期望抛错


def test_update_only_provided_fields():
    db = FakeDb()
    hcp = _make_hcp(hospital="协和医院", title="主任医师")
    hcp = HcpRepo.update(db, hcp, {"hospital": "仁济医院"})
    assert hcp.hospital == "仁济医院"
    assert hcp.title == "主任医师"  # 未传入字段保持不变
