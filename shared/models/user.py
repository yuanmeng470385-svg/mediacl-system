"""用户模型"""
from sqlalchemy import Column, String, BigInteger, ForeignKey
from shared.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    username = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))
    role = Column(String(20), nullable=False)
    region = Column(String(50))
    manager_id = Column(BigInteger, ForeignKey("users.id"))
    status = Column(String(20), default="active")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "full_name": self.full_name,
            "phone": self.phone,
            "email": self.email,
            "role": self.role,
            "region": self.region,
            "status": self.status,
        }
