"""
密码与验证码的密码学工具

- 密码：bcrypt（自带盐）。password_hash 为 None 表示未设置密码，一律拒绝登录。
- 验证码：secrets 生成，constant-time 比较，避免时序侧信道。
"""

import hmac
import secrets
import logging
from typing import Optional

import bcrypt

logger = logging.getLogger(__name__)

# bcrypt 只取密码前 72 字节，超长直接拒绝，避免"改了后半段密码仍能登录"
MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    pass


def hash_password(plain: str) -> str:
    """生成 bcrypt 哈希"""
    raw = plain.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(f"密码不能超过 {MAX_PASSWORD_BYTES} 字节")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: Optional[str]) -> bool:
    """校验密码。hashed 为空（未设置密码）时恒为 False。"""
    if not hashed:
        return False
    raw = plain.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # 哈希格式损坏 —— 记日志但不泄露给调用方
        logger.warning("password_hash 格式异常，按验证失败处理")
        return False


def generate_code(length: int = 6) -> str:
    """生成纯数字验证码"""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def codes_equal(a: Optional[str], b: Optional[str]) -> bool:
    """constant-time 比较验证码"""
    if not a or not b:
        return False
    return hmac.compare_digest(a, b)
