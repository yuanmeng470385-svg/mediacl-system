"""医生档案 Excel 批量导入解析（openpyxl）

表头约定（第一行）：
    姓名(必填) | 医院 | 科室 | 职称 | 专业 | 电话 | 邮箱 | 区域 | 影响力 | 标签(逗号分隔)
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# 中文表头 → 模型字段
COLUMN_MAP = {
    "姓名": "name",
    "医院": "hospital",
    "科室": "department",
    "职称": "title",
    "专业": "specialty",
    "电话": "phone",
    "邮箱": "email",
    "区域": "region",
    "影响力": "influence_level",
    "标签": "tags",
}

# 影响力中文 → 枚举值
_INFLUENCE_MAP = {"高": "high", "中": "medium", "低": "low", "high": "high", "medium": "medium", "low": "low"}

# M13（2026-08-21 审计）：xlsx 本质是 zip，小文件可解压出巨型工作表（解压炸弹）。
# 行/列上限防 iter_rows 无界展开撑爆内存；超限抛 ValueError，端点统一转 ParamError。
MAX_IMPORT_ROWS = 5000
MAX_IMPORT_COLS = 200


def parse_hcp_excel(file) -> List[Dict]:
    """解析医生档案 Excel（第一个工作表），跳过空行，返回 [{name, hospital, ...}]

    Args:
        file: 类文件对象（UploadFile.file 或已打开的路径）

    Returns:
        解析出的行列表；未识别到有效表头/数据时返回 []
    """
    from openpyxl import load_workbook

    wb = load_workbook(file, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)

    header = next(rows, None)
    if not header:
        return []
    if len(header) > MAX_IMPORT_COLS:
        raise ValueError(f"Excel 列数 {len(header)} 超过上限 {MAX_IMPORT_COLS}（疑似损坏文件或压缩炸弹）")

    col_map = {}
    for idx, cell in enumerate(header):
        if cell is not None and str(cell).strip() in COLUMN_MAP:
            col_map[idx] = COLUMN_MAP[str(cell).strip()]

    if "name" not in col_map.values():
        logger.warning("Excel 缺少必填表头「姓名」")
        return []

    result = []
    for row in rows:
        if len(result) >= MAX_IMPORT_ROWS:
            raise ValueError(
                f"Excel 数据行数超过上限 {MAX_IMPORT_ROWS}（疑似损坏文件或压缩炸弹），请分批导入")
        item = {}
        for idx, field in col_map.items():
            val = row[idx] if idx < len(row) else None
            if val is None:
                continue
            val = str(val).strip()
            if field == "influence_level":
                item[field] = _INFLUENCE_MAP.get(val, val)
            else:
                item[field] = val
        if item.get("name"):  # 姓名必填，跳过空行
            result.append(item)
    return result
