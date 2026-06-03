"""
Redis 键值存储 — KeyValueStore 的 Redis 实现
"""
from __future__ import annotations

from typing import Optional


class RedisKeyValueStore:
    """基于 Redis 的键值存储"""

    def __init__(self, redis_url: str) -> None:
        import redis
        self._redis = redis.from_url(redis_url, decode_responses=True)

    def get(self, namespace: str, key: str) -> Optional[str]:
        return self._redis.hget(namespace, key)

    def set(self, namespace: str, key: str, value: str, ttl: int | None = None) -> None:
        self._redis.hset(namespace, key, value)
        if ttl:
            self._redis.expire(namespace, ttl)

    def delete(self, namespace: str, key: str) -> None:
        self._redis.hdel(namespace, key)

    def get_all(self, namespace: str) -> dict[str, str]:
        return self._redis.hgetall(namespace) or {}

    def clear(self, namespace: str) -> None:
        self._redis.delete(namespace)
