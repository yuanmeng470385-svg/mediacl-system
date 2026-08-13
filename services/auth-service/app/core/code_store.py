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


# 原子消耗验证码尝试次数（B5 修复 2026-08-12）：
#   GET → 递增 attempts → 超限 DEL / 未超限 SETEX（保留剩余 TTL）
#   返回值 {state, code}：state 0=无验证码 / 1=可校验 / 2=已用尽（验证码已作废）
_TAKE_ATTEMPT_LUA = """
local raw = redis.call('GET', KEYS[1])
if not raw then
  return {0, ''}
end
local data = cjson.decode(raw)
data.attempts = data.attempts + 1
if data.attempts > tonumber(ARGV[1]) then
  redis.call('DEL', KEYS[1])
  return {2, data.code}
end
local remaining = redis.call('TTL', KEYS[1])
if remaining < 1 then
  remaining = 1
end
redis.call('SETEX', KEYS[1], remaining, cjson.encode(data))
return {1, data.code}
"""


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
            # 原子消耗（B5 修复 2026-08-12）：旧实现 GET→修改→SETEX 非原子 ——
            # 并发登录请求同时读到同一 attempts 值，验证码可被并发重放。
            # Lua 单脚本内完成 读→递增→超限作废/回写，Redis 单线程保证串行。
            # 返回 {state, code}：state 0=无验证码 / 1=可校验 / 2=已用尽（验证码已作废）
            state, code = self._redis.eval(
                _TAKE_ATTEMPT_LUA, 1, _key(phone), str(int(max_attempts))
            )
            state = int(state)
            if state == 2:
                return code or None, True
            if state == 0:
                return None, False
            return code or None, False
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
