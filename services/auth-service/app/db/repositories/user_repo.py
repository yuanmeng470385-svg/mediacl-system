"""用户数据访问层（认证用，只读 + 改密码）"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from shared.models.user import User

logger = logging.getLogger(__name__)


class UserRepo:
    """用户仓库"""

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_by_phone(db: Session, phone: str) -> Optional[User]:
        return db.query(User).filter(User.phone == phone).first()

    @staticmethod
    def is_active(user: Optional[User]) -> bool:
        return bool(user) and user.status == "active"

    @staticmethod
    def set_password(db: Session, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        db.commit()
        db.refresh(user)
        return user
