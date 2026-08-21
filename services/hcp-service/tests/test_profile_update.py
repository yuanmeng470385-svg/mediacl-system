"""画像更新合并语义（JSONB 按 key 合并，不覆盖已有值）"""
from app.db.repositories.hcp_repo import _merge_profile_fields


def test_merge_fills_empty_keys():
    base = {"academic_background": {"school": "XX医科大学", "degree": "博士"}}
    updates = {"academic_background": {"research_interest": "肺癌免疫治疗"}}
    merged = _merge_profile_fields(base, updates)
    assert merged["academic_background"]["school"] == "XX医科大学"
    assert merged["academic_background"]["research_interest"] == "肺癌免疫治疗"


def test_merge_never_overwrites_existing():
    base = {"academic_background": {"school": "XX医科大学"}}
    updates = {"academic_background": {"school": "被篡改"}}
    merged = _merge_profile_fields(base, updates)
    assert merged["academic_background"]["school"] == "XX医科大学"


def test_tags_dedup_append():
    base = {"tags": ["KOL"]}
    merged = _merge_profile_fields(base, {"tags": ["KOL", "学术型"]})
    assert merged["tags"] == ["KOL", "学术型"]


def test_tags_string_comma_split_not_char_iteration():
    """修复前 `for tag in value:` 对字符串逐字符展开 → "KOL,学术型" 变成
    ["K","O","L",",","学",...] 单字符标签污染画像（审计遗留）。"""
    merged = _merge_profile_fields({"tags": ["KOL"]}, {"tags": "KOL,学术型"})
    assert merged["tags"] == ["KOL", "学术型"]
