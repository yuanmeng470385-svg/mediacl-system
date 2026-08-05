"""用户模型"""
from sqlalchemy import Column, String, BigInteger, ForeignKey
from shared.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    username = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))
    password_hash = Column(String(255))   # bcrypt；None = 未设置密码，禁止密码登录
    role = Column(String(20), nullable=False)
    region = Column(String(50))
    manager_id = Column(BigInteger, ForeignKey("users.id"))
    status = Column(String(20), default="active")

    def to_dict(self):
        """对外输出。注意：绝不包含 password_hash。"""
        return {
            "id": self.id,
            "username": self.username,
            "full_name": self.full_name,
            # 移动端/Web 前端读的是 name，这里一并给出，避免两端各自映射
            "name": self.full_name,
            "phone": self.phone,
            "email": self.email,
            "role": self.role,
            "region": self.region,
            "status": self.status,
        }
