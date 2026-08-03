"""Excel 批量导入解析测试"""
import os
import sys
import io
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.excel_parser import parse_hcp_excel  # noqa: E402
from openpyxl import Workbook  # noqa: E402


def _make_xlsx(headers, rows):
    """生成内存 xlsx 文件对象"""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_parse_basic():
    buf = _make_xlsx(
        ["姓名", "医院", "科室", "职称", "影响力", "标签"],
        [
            ["张伟", "协和医院", "肿瘤内科", "主任医师", "高", "KOL,学术型"],
            ["李娜", "仁济医院", "呼吸科", "副主任医师", "中", ""],
            ["", "空行医院", "", "", "", ""],  # 姓名为空，应跳过
        ],
    )
    rows = parse_hcp_excel(buf)
    assert len(rows) == 2
    assert rows[0]["name"] == "张伟"
    assert rows[0]["hospital"] == "协和医院"
    assert rows[0]["influence_level"] == "high"  # 中文映射
    assert rows[0]["tags"] == "KOL,学术型"  # 逗号分隔，入库时再转列表
    assert rows[1]["influence_level"] == "medium"


def test_parse_missing_required_header():
    """缺少「姓名」表头 → 返回空列表"""
    buf = _make_xlsx(["医院", "科室"], [["协和医院", "肿瘤内科"]])
    assert parse_hcp_excel(buf) == []


def test_parse_empty_file():
    """只有表头没有数据 → 返回空列表"""
    buf = _make_xlsx(["姓名", "医院"], [])
    assert parse_hcp_excel(buf) == []


def test_parse_unknown_columns_ignored():
    """不认识的列被忽略，不报错"""
    buf = _make_xlsx(["姓名", "随便写的列"], [["王五", "foo"]])
    rows = parse_hcp_excel(buf)
    assert len(rows) == 1
    assert rows[0]["name"] == "王五"
    assert "随便写的列" not in rows[0]
