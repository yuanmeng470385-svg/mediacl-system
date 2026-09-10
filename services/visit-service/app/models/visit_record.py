"""拜访记录数据模型（re-export）

模型本体在 shared/models/visit.py —— visit-service 与 specialist-service
共用（分身从历史记录生成风格需读拜访转写），照 digital_specialist 的
shared 模式；模型依赖的状态常量随模型在 shared 维护。
"""
from shared.models.visit import VisitRecord  # noqa: F401
