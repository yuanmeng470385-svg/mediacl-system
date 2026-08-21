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


def test_report_export_formula_injection_sanitized():
    """公式注入防护（审计 M4 铺开）：拦截 content / 规则字段 / 汇总拼接串以
    = + - @ 开头时必须加 ' 前缀，防止报告被 Excel 打开时执行公式。"""
    from app.api.report import build_report_workbook
    evil_content = '=HYPERLINK("http://evil.example","点此领取")'
    rules = [
        {"rule_code": "=R900", "rule_name": "+恶意规则", "rule_type": "keyword",
         "severity": "high", "action": "reject", "enabled": True, "version": 1, "hit_count": 3},
    ]
    blocks = [
        {"id": 1, "user_id": 1, "service_name": "specialist", "content": evil_content,
         "rule_code": "=R900", "rule_name": "+恶意规则", "severity": "high",
         "action": "reject", "blocked_at": datetime(2026, 8, 1, 10, 0, 0)},
        {"id": 2, "user_id": 2, "service_name": "visit", "content": "+7020",
         "rule_code": "=R900", "rule_name": "+恶意规则", "severity": "high",
         "action": "warn", "blocked_at": datetime(2026, 8, 2, 11, 0, 0)},
    ]
    summary = {"by_rule": [("-R900", 3)], "by_service": [("specialist", 3)],
               "by_day": [("2026-08-01", 3)], "action_ratio": {"reject": 1.0, "warn": 0.0, "log": 0.0}}
    wb = build_report_workbook(rules, blocks, summary)
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    wb2 = load_workbook(bio)
    ws_rules = wb2["规则快照"]
    assert ws_rules.cell(row=2, column=1).value == "'=R900"
    assert ws_rules.cell(row=2, column=2).value == "'+恶意规则"
    ws_blocks = wb2["拦截明细"]
    assert ws_blocks.cell(row=2, column=4).value == "'" + evil_content
    assert ws_blocks.cell(row=3, column=4).value == "'+7020"
    ws_sum = wb2["汇总"]
    assert ws_sum.cell(row=2, column=2).value == "'-R900: 3"   # 汇总 f-string 拼接同样要防
