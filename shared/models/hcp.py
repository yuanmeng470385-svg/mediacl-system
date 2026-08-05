"""医生/专家数据模型（共享）

hcp-service 与 visit-service 共用：visit_records.hcp_id 外键引用了 hcps 表，
visit-service 侧必须注册本模型才能解析 FK 元数据。
"""

from sqlalchemy import Column, String, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from shared.models.base import Base, TimestampMixin


class Hcp(Base, TimestampMixin):
    """医生/专家档案（映射 hcps 表）"""
    __tablename__ = "hcps"

    name = Column(String(100), nullable=False)
    hospital = Column(String(200))
    department = Column(String(100))
    title = Column(String(50))              # 职称：主任医师/副主任医师/主治医师...
    specialty = Column(String(100))         # 专业方向
    phone = Column(String(20))
    email = Column(String(100))
    region = Column(String(50))             # 区域
    academic_background = Column(JSONB)     # 学术背景（学历/学会任职/科研）
    prescription_preference = Column(JSONB) # 处方偏好（偏好品牌/剂量/联合方案）
    influence_level = Column(String(20))    # 影响力：high / medium / low
    tags = Column(JSONB)                    # 标签列表 ["肿瘤科KOL", "学术型"]
    status = Column(String(20), default="active")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "hospital": self.hospital,
            "department": self.department,
            "title": self.title,
            "specialty": self.specialty,
            "phone": self.phone,
            "email": self.email,
            "region": self.region,
            "academic_background": self.academic_background,
            "prescription_preference": self.prescription_preference,
            "influence_level": self.influence_level,
            "tags": self.tags or [],
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
