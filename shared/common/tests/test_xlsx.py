"""共享 xlsx 单元格清洗（公式注入防护）— specialist _sanitize_cell 上收为共享工具"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def test_sanitize_cell_escapes_formula_prefixes():
    """= + - @ \t \r 开头的字符串必须加 ' 前缀（openpyxl 会当公式执行）"""
    from shared.common.xlsx import sanitize_cell

    for evil in ("=1+1", "+7020", "-2+3+cmd", "@SUM(x)", "\tx", "\rx"):
        assert sanitize_cell(evil) == "'" + evil, evil


def test_sanitize_cell_keeps_normal_values():
    """普通字符串 / 数字 / None 原样返回，不误伤"""
    from shared.common.xlsx import sanitize_cell

    assert sanitize_cell("普通文本") == "普通文本"
    assert sanitize_cell("协和-301") == "协和-301"   # 中文间连字符不以 - 开头，不能误加 '
    assert sanitize_cell(123) == 123
    assert sanitize_cell(0) == 0
    assert sanitize_cell("") == ""
    assert sanitize_cell(None) is None
