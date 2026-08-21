"""xlsx 导出工具 — 公式注入防护（审计 M4 统一收口）

specialist-service data_exports 原有实现上收为共享工具，
compliance 报告导出 / audit 日志导出等所有 xlsx 出口统一使用。
"""
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value):
    """以公式触发字符（= + - @ \t \r）开头的字符串加 ' 前缀，强制存为文本。

    openpyxl 会把这类字符串当公式写入，导出文件被 Excel/WPS 打开时可能执行
    （如 =HYPERLINK(...)/=cmd|' /C ...'）。仅处理非空 str；数字/None/空串原样返回。
    """
    if isinstance(value, str) and value and value[0] in _FORMULA_PREFIXES:
        return "'" + value
    return value
