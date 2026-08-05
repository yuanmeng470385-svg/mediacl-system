"""监管自查报告导出单测（真实 openpyxl 写文件，读回断言）"""
import io
from datetime import datetime

import pytest
from openpyxl import load_workbook
from fastapi import Depends

from shared.common.response import success


def _build_rows():
    """构造与报告生成同构的数据（绕过 DB，直接测 Excel 组装函数）"""
    from app.api.report import build_report_workbook
    rules = [
        {"rule_code": "R001", "rule_name": "禁止承诺疗效", "rule_type": "keyword",
         "severity": "high", "action": "reject", "enabled": True, "version": 1, "hit_count": 3},
    ]
    blocks = [
        {"id": 1, "user_id": 1, "service_name": "specialist", "content": "保证治好",
         "rule_code": "R001", "rule_name": "禁止承诺疗效", "severity": "high",
         "action": "reject", "blocked_at": datetime(2026, 8, 1, 10, 0, 0)},
    ]
    summary = {"by_rule": [("R001", 3)], "by_service": [("specialist", 3)],
               "by_day": [("2026-08-01", 3)], "action_ratio": {"reject": 1.0, "warn": 0.0, "log": 0.0}}
    wb = build_report_workbook(rules, blocks, summary)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    wb2 = load_workbook(bio)
    assert wb2.sheetnames == ["规则快照", "拦截明细", "汇总"]
    ws = wb2["规则快照"]
    headers = [c.value for c in ws[1]]
    assert "rule_code" in headers and "hit_count" in headers
    assert ws.max_row >= 2
    ws2 = wb2["拦截明细"]
    assert ws2.max_row >= 2


def test_report_export():
    """pytest 默认只收集 test* 开头的函数，_build_rows 需经此入口执行"""
    _build_rows()
