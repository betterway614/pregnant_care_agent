"""
内存键值存储 — KeyValueStore 的轻量级实现

当未配置 Redis 时使用，数据不持久化。
"""
from __future__ import annotations

import threading
from typing import Optional


class InMemoryKeyValueStore:
    """基于字典的内存键值存储，线程安全"""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()

    def get(self, namespace: str, key: str) -> Optional[str]:
        with self._lock:
            return self._data.get(namespace, {}).get(key)

    def set(self, namespace: str, key: str, value: str, ttl: int | None = None) -> None:
        with self._lock:
            if namespace not in self._data:
                self._data[namespace] = {}
            self._data[namespace][key] = value

    def delete(self, namespace: str, key: str) -> None:
        with self._lock:
            if namespace in self._data:
                self._data[namespace].pop(key, None)

    def get_all(self, namespace: str) -> dict[str, str]:
        with self._lock:
            return dict(self._data.get(namespace, {}))

    def clear(self, namespace: str) -> None:
        with self._lock:
            self._data.pop(namespace, None)
