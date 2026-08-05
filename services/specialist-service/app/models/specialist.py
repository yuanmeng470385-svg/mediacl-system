"""数字专员数据模型（re-export）

模型本体在 shared/models/digital_specialist.py —— specialist-service 与
visit-service 共用，visit-service 需注册 digital_specialists 元数据以解析
visit_records.specialist_id 外键。
"""
from shared.models.digital_specialist import Specialist  # noqa: F401
