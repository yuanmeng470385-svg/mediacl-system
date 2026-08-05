"""医生/专家数据模型（re-export）

模型本体在 shared/models/hcp.py —— hcp-service 与 visit-service 共用，
visit-service 需注册 hcps 元数据以解析 visit_records.hcp_id 外键。
"""
from shared.models.hcp import Hcp  # noqa: F401
