"""HCP 画像 Redis 缓存（2026-08-11 修复：画像无缓存，详情页每次实时查库 + LLM）

背景：画像读多写少（详情页每次打开实时查库 + profile 端点每次调 LLM 付费），
写路径低频（拜访结束 profile-update + admin 编辑）。Redis 早已部署（REDIS_URL
配置但从未使用）——接上读路径缓存 + 写路径失效，画像分钟级新鲜度。

设计：
- 键前缀 hcpcache:，两个键：hcp:{id}（档案行 to_dict）、profile:{id}（画像端点完整结果含 LLM）
- TTL 300s 兜底一致性；写路径（PUT/tags/profile-update）即时失效
- Redis 不可用：fail-open 无缓存（缓存是性能优化非安全控制），warning 日志节流（60s 一条）
- visit-service 同库直读 hcps 不走本缓存（每次拜访 2 次单行查询，成本低）
"""
import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300  # 秒：画像低频变化，TTL 兜底新鲜度；写路径即时失效


class HcpCache:
    def __init__(self, redis_url: Optional[str] = None, ttl: int = DEFAULT_TTL):
        self._redis = None
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.ttl = ttl
        self._warned_at = 0.0

    def _client(self):
        """懒建连接（照搬 auth-service code_store.py：快速失败超时，不拖慢请求）"""
        if self._redis is None:
            import redis
            self._redis = redis.Redis.from_url(
                self._redis_url, decode_responses=True,
                socket_timeout=1, socket_connect_timeout=1,
            )
        return self._redis

    def _unavailable(self, exc: Exception) -> None:
        """Redis 不可用：warning 节流（60s 一条），fail-open 无缓存"""
        now = time.time()
        if now - self._warned_at >= 60:
            logger.warning("HCP 缓存 Redis 不可用（本次请求回源查库，无缓存）: %s", exc)
            self._warned_at = now

    def get(self, key: str) -> Optional[dict]:
        try:
            raw = self._client().get(f"hcpcache:{key}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            self._unavailable(exc)
            return None

    def set(self, key: str, value: dict) -> None:
        try:
            self._client().set(
                f"hcpcache:{key}", json.dumps(value, ensure_ascii=False), ex=self.ttl,
            )
        except Exception as exc:
            self._unavailable(exc)

    def invalidate(self, *keys: str) -> None:
        """写路径失效：删除对应缓存键（缺失键忽略）"""
        try:
            client = self._client()
            for k in keys:
                client.delete(f"hcpcache:{k}")
        except Exception as exc:
            self._unavailable(exc)

    def invalidate_profile(self, hcp_id: int) -> None:
        """写路径失效画像：删除该医生的全部查看者变体（H3 分键后前缀扫删）。

        画像键现为 profile:{id}:all（admin/manager 全量）与 profile:{id}:u{uid}
        （rep 本人视角），不再只删一个键；同时兼容删除历史单键 profile:{id}。

        E6（2026-08-13）：扫描模式必须带冒号 hcpcache:profile:{hcp_id}:* ——
        无冒号的 profile:{hcp_id}* 会把更大编号医生误伤（如写 hcp 1 时
        profile:1* 命中 profile:10:all / 11 / 100，付费画像缓存被误删）。
        历史单键 profile:{id} 无后缀，单独精确删除，保持原兼容承诺。
        """
        try:
            client = self._client()
            for key in client.scan_iter(f"hcpcache:profile:{hcp_id}:*", count=100):
                client.delete(key)
            client.delete(f"hcpcache:profile:{hcp_id}")  # H3 之前的历史单键
        except Exception as exc:
            self._unavailable(exc)


# 模块级单例（懒连接，服务内共享）
cache = HcpCache()
