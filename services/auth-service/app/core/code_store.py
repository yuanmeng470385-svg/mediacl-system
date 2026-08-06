"""
验证码存储

认证是安全边界，这一层**不允许 fail-open**：Redis 不可用时必须抛错，
让 send-code / login 直接失败，而不是"放行"。

- RedisCodeStore：生产用。带 TTL、重发冷却、尝试次数上限。
- MemoryCodeStore：仅供单元测试注入，不在生产代码路径里被选中。
"""

import time
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class CodeStoreError(RuntimeError):
    """存储不可用。调用方应转成 5xx，绝不能当作"验证通过"。"""


class CodeStore(ABC):
    """验证码存储接口"""

    @abstractmethod
    def in_cooldown(self, phone: str) -> int:
        """返回还需等待的秒数；0 表示可以发送"""

    @abstractmethod
    def save(self, phone: str, code: str, ttl: int, cooldown: int) -> None:
        """写入验证码并起冷却计时"""

    @abstractmethod
    def take_attempt(self, phone: str, max_attempts: int) -> Tuple[Optional[str], bool]:
        """
        消耗一次校验机会。

        语义：单个验证码最多可校验 max_attempts 次。第 1..max_attempts 次
        （含最后一次）都返回 exhausted=False，可正常校验；第 max_attempts 次
        之后（即下一次调用）才返回 exhausted=True，验证码随之作废。

        Returns:
            (code, exhausted)
            code      — 当前存储的验证码，不存在/已过期则为 None
            exhausted — 尝试次数已用尽（此时验证码已被作废）
        """

    @abstractmethod
    def drop(self, phone: str) -> None:
        """校验成功后立即作废，防止重放"""


def _key(phone: str) -> str:
    return f"authcode:{phone}"


def _cooldown_key(phone: str) -> str:
    return f"authcode:cd:{phone}"


class RedisCodeStore(CodeStore):
    """Redis 实现"""

    def __init__(self, redis_url: str):
        try:
            import redis  # 延迟导入：单测走 MemoryCodeStore 时无需安装
        except ImportError as exc:  # pragma: no cover
            raise CodeStoreError("未安装 redis 包，无法启用验证码存储") from exc
        self._redis = redis.Redis.from_url(
            redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
        )

    def in_cooldown(self, phone: str) -> int:
        try:
            ttl = self._redis.ttl(_cooldown_key(phone))
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc
        return ttl if ttl and ttl > 0 else 0

    def save(self, phone: str, code: str, ttl: int, cooldown: int) -> None:
        payload = json.dumps({"code": code, "attempts": 0, "created_at": int(time.time())})
        try:
            pipe = self._redis.pipeline()
            pipe.setex(_key(phone), ttl, payload)
            pipe.setex(_cooldown_key(phone), cooldown, "1")
            pipe.execute()
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc

    def take_attempt(self, phone: str, max_attempts: int) -> Tuple[Optional[str], bool]:
        try:
            raw = self._redis.get(_key(phone))
            if not raw:
                return None, False
            data = json.loads(raw)
            data["attempts"] = int(data.get("attempts", 0)) + 1
            if data["attempts"] > max_attempts:
                # 已超过上限：作废验证码，本次调用起报告 exhausted
                self._redis.delete(_key(phone))
                return data.get("code"), True
            # 第 max_attempts 次（最后一次机会）仍允许校验，下次调用才作废
            # 保留剩余 TTL，不因为一次失败而延长有效期
            remaining = self._redis.ttl(_key(phone))
            self._redis.setex(_key(phone), max(remaining, 1), json.dumps(data))
            return data.get("code"), False
        except CodeStoreError:
            raise
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc

    def drop(self, phone: str) -> None:
        try:
            self._redis.delete(_key(phone))
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc


class MemoryCodeStore(CodeStore):
    """进程内实现 —— 只给单元测试用，多进程下不可靠"""

    def __init__(self):
        self._codes: dict = {}
        self._cooldowns: dict = {}

    def in_cooldown(self, phone: str) -> int:
        expire = self._cooldowns.get(phone, 0)
        remaining = int(expire - time.time())
        return remaining if remaining > 0 else 0

    def save(self, phone: str, code: str, ttl: int, cooldown: int) -> None:
        self._codes[phone] = {"code": code, "attempts": 0, "expire": time.time() + ttl}
        self._cooldowns[phone] = time.time() + cooldown

    def take_attempt(self, phone: str, max_attempts: int) -> Tuple[Optional[str], bool]:
        entry = self._codes.get(phone)
        if not entry or entry["expire"] < time.time():
            self._codes.pop(phone, None)
            return None, False
        entry["attempts"] += 1
        if entry["attempts"] > max_attempts:
            self._codes.pop(phone, None)
            return entry["code"], True
        return entry["code"], False

    def drop(self, phone: str) -> None:
        self._codes.pop(phone, None)
