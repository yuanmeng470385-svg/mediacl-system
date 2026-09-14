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
import threading
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class CodeStoreError(RuntimeError):
    """存储不可用。调用方应转成 5xx，绝不能当作"验证通过"。"""


# consume() 返回状态
CONSUME_NOTFOUND = "notfound"    # 无验证码：未发送 / 已过期 / 已作废
CONSUME_MATCHED = "matched"      # 匹配成功，验证码已在同一原子操作内作废
CONSUME_MISMATCH = "mismatch"    # 不匹配，已消耗一次尝试（仍在上限内）
CONSUME_EXHAUSTED = "exhausted"  # 尝试次数用尽，验证码已作废


# 验证码场景：login=登录（只对已注册号发，键格式保持历史不变）；
# register=医生自助注册（只对未注册号发，独立键命名空间，两场景的码互不通用，
# 注册码不能拿来登录、登录码不能拿来注册）
SCENE_LOGIN = "login"
SCENE_REGISTER = "register"

# 日限的滚动窗口（非自然日）：首个验证码发出后 24h 内计数
_DAILY_WINDOW_SECONDS = 86400


class CodeStore(ABC):
    """验证码存储接口"""

    @abstractmethod
    def in_cooldown(self, phone: str, scene: str = SCENE_LOGIN) -> int:
        """返回还需等待的秒数；0 表示可以发送"""

    @abstractmethod
    def save(self, phone: str, code: str, ttl: int, cooldown: int, scene: str = SCENE_LOGIN) -> bool:
        """写入验证码并起冷却计时。

        A9（并发安全）：验证码键用 SET NX 语义——键已存在（并发请求已先
        写入）时返回 False 且不覆盖已有验证码，调用方按冷却处理，防止并发
        双发互相覆盖（后到者覆盖先发码会让用户拿到废码）。写入成功返回 True。
        """

    @abstractmethod
    def consume(self, phone: str, code: str, max_attempts: int, scene: str = SCENE_LOGIN) -> str:
        """
        原子「校验并消耗」验证码：比较与作废必须在同一原子操作内完成，
        防止两个并发请求携带同一正确码各自通过校验（签出多个 token）。

        语义：单个验证码最多可校验 max_attempts 次。每次调用（无论对错）
        消耗一次尝试；第 1..max_attempts 次调用正常比对，第 max_attempts
        次之后（即下一次调用）返回 CONSUME_EXHAUSTED，验证码随之作废
        （用尽后任何输入都被拒）。匹配成功立即作废。

        Returns:
            CONSUME_NOTFOUND / CONSUME_MATCHED / CONSUME_MISMATCH / CONSUME_EXHAUSTED
        """

    @abstractmethod
    def drop(self, phone: str, scene: str = SCENE_LOGIN) -> None:
        """校验成功后立即作废，防止重放"""

    @abstractmethod
    def daily_count(self, phone: str) -> int:
        """滚动 24h 窗口内该手机号已实际发出的验证码条数（跨场景累计）"""

    @abstractmethod
    def bump_daily(self, phone: str) -> None:
        """实际发出一条验证码后计数 +1（滚动 24h 窗口）"""


def _key(phone: str, scene: str = SCENE_LOGIN) -> str:
    if scene == SCENE_REGISTER:
        return f"authcode:reg:{phone}"
    return f"authcode:{phone}"


def _cooldown_key(phone: str, scene: str = SCENE_LOGIN) -> str:
    if scene == SCENE_REGISTER:
        return f"authcode:regcd:{phone}"
    return f"authcode:cd:{phone}"


def _daily_key(phone: str) -> str:
    # 日限跨场景共享（按手机号计），SMS 成本护栏
    return f"authcode:daily:{phone}"


# 原子校验并消耗验证码（H1 修复 2026-08-13）：
#   B5（2026-08-12）只把「尝试计数」原子化了，比较在 Python 侧、作废是
#   第三次独立调用 —— 两个并发请求携带同一正确码时，两次比较都能通过，
#   各自签出 token。本脚本把「计数 + 比较 + 命中即 DEL」收进同一个 Lua
#   脚本，Redis 单线程串行执行，验证码只能被消耗一次。
#   尝试次数语义与旧 take_attempt 完全一致：每次调用（无论对错）先消耗
#   一次尝试，超过 max_attempts 即作废 —— 用尽后任何输入（包括正确码）
#   都被拒（见 tests/test_auth.py 既有用例）。
#   返回值 {state}：state 0=无验证码 / 1=匹配成功（已作废）/
#   2=不匹配（仍在尝试上限内）/ 3=尝试用尽（验证码已作废）
_CONSUME_LUA = """
-- 常量时间比较：验证码只有 6 位数字且比较发生在 Redis 进程内（不跨网络），
-- 时序侧信道本身很弱，仍按既有约定逐字节比较、不提前退出。
local function cteq(a, b)
  local n = #a
  if #b > n then
    n = #b
  end
  local diff = 0
  for i = 1, n do
    local ba = 0
    local bb = 0
    if i <= #a then
      ba = string.byte(a, i)
    end
    if i <= #b then
      bb = string.byte(b, i)
    end
    if ba ~= bb then
      diff = diff + 1
    end
  end
  return diff == 0
end

local raw = redis.call('GET', KEYS[1])
if not raw then
  return {0}
end
local data = cjson.decode(raw)
data.attempts = data.attempts + 1
if data.attempts > tonumber(ARGV[2]) then
  redis.call('DEL', KEYS[1])
  return {3}
end
if cteq(data.code, ARGV[1]) then
  redis.call('DEL', KEYS[1])
  return {1}
end
local remaining = redis.call('TTL', KEYS[1])
if remaining < 1 then
  remaining = 1
end
redis.call('SETEX', KEYS[1], remaining, cjson.encode(data))
return {2}
"""


# A9：save 的「SET NX + 冷却写」收进同一 Lua 脚本，Redis 单线程原子执行：
#   并发双发只有一个写入成功（返回 1），后到者返回 0 且不重置先发者的冷却计时。
_SAVE_NX_LUA = """
if redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]), 'NX') then
  redis.call('SETEX', KEYS[2], tonumber(ARGV[3]), '1')
  return {1}
end
return {0}
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

    def in_cooldown(self, phone: str, scene: str = SCENE_LOGIN) -> int:
        try:
            ttl = self._redis.ttl(_cooldown_key(phone, scene))
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc
        return ttl if ttl and ttl > 0 else 0

    def save(self, phone: str, code: str, ttl: int, cooldown: int, scene: str = SCENE_LOGIN) -> bool:
        payload = json.dumps({"code": code, "attempts": 0, "created_at": int(time.time())})
        try:
            return bool(
                self._redis.eval(
                    _SAVE_NX_LUA,
                    2,
                    _key(phone, scene),
                    _cooldown_key(phone, scene),
                    payload,
                    str(int(ttl)),
                    str(int(cooldown)),
                )[0]
            )
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc

    def consume(self, phone: str, code: str, max_attempts: int, scene: str = SCENE_LOGIN) -> str:
        try:
            # 原子校验并消耗（H1 修复 2026-08-13）：比较与作废在同一 Lua 脚本内，
            # Redis 单线程保证两个并发请求只有一个能 matched。
            state = int(
                self._redis.eval(
                    _CONSUME_LUA, 1, _key(phone, scene), code, str(int(max_attempts))
                )[0]
            )
            return (
                CONSUME_NOTFOUND,
                CONSUME_MATCHED,
                CONSUME_MISMATCH,
                CONSUME_EXHAUSTED,
            )[state]
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc

    def drop(self, phone: str, scene: str = SCENE_LOGIN) -> None:
        try:
            self._redis.delete(_key(phone, scene))
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc

    def daily_count(self, phone: str) -> int:
        try:
            raw = self._redis.get(_daily_key(phone))
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc
        return int(raw) if raw else 0

    def bump_daily(self, phone: str) -> None:
        try:
            n = self._redis.incr(_daily_key(phone))
            if n == 1:
                # INCR 与 EXPIRE 之间崩溃会留下无 TTL 键（该号被永久限额）。
                # 窗口极小、概率可忽略，且方向是"宁紧勿松"（SMS 成本护栏）
                self._redis.expire(_daily_key(phone), _DAILY_WINDOW_SECONDS)
        except Exception as exc:
            raise CodeStoreError(f"Redis 不可用: {exc}") from exc


class MemoryCodeStore(CodeStore):
    """进程内实现 —— 只给单元测试用，多进程下不可靠"""

    def __init__(self):
        self._codes: dict = {}
        self._cooldowns: dict = {}
        self._daily: dict = {}
        # 模拟 Redis 单线程语义：consume 整段持锁，并发下验证码也只消耗一次
        self._lock = threading.Lock()

    def in_cooldown(self, phone: str, scene: str = SCENE_LOGIN) -> int:
        expire = self._cooldowns.get((phone, scene), 0)
        remaining = int(expire - time.time())
        return remaining if remaining > 0 else 0

    def save(self, phone: str, code: str, ttl: int, cooldown: int, scene: str = SCENE_LOGIN) -> bool:
        # 模拟 Redis SET NX 语义（A9）：键已存在（未过期）时不覆盖、返回 False
        entry = self._codes.get((phone, scene))
        if entry and entry["expire"] > time.time():
            return False
        self._codes[(phone, scene)] = {"code": code, "attempts": 0, "expire": time.time() + ttl}
        self._cooldowns[(phone, scene)] = time.time() + cooldown
        return True

    def consume(self, phone: str, code: str, max_attempts: int, scene: str = SCENE_LOGIN) -> str:
        with self._lock:
            entry = self._codes.get((phone, scene))
            if not entry or entry["expire"] < time.time():
                self._codes.pop((phone, scene), None)
                return CONSUME_NOTFOUND
            entry["attempts"] += 1
            if entry["attempts"] > max_attempts:
                self._codes.pop((phone, scene), None)
                return CONSUME_EXHAUSTED
            if entry["code"] == code:
                self._codes.pop((phone, scene), None)
                return CONSUME_MATCHED
            return CONSUME_MISMATCH

    def drop(self, phone: str, scene: str = SCENE_LOGIN) -> None:
        self._codes.pop((phone, scene), None)

    def daily_count(self, phone: str) -> int:
        entry = self._daily.get(phone)
        if not entry or entry[1] < time.time():
            self._daily.pop(phone, None)
            return 0
        return entry[0]

    def bump_daily(self, phone: str) -> None:
        entry = self._daily.get(phone)
        if not entry or entry[1] < time.time():
            self._daily[phone] = [1, time.time() + _DAILY_WINDOW_SECONDS]
        else:
            entry[0] += 1
