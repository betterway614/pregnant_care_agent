"""
键值存储接口 — 替代 MemoryManager 中 Redis/内存的 if/else 分支

遵循 OCP: 新增存储后端只需实现此协议，无需修改 MemoryManager。
遵循 DIP: MemoryManager 依赖此抽象，而非具体 Redis 客户端。
"""
from __future__ import annotations

from typing import Optional, Protocol


class KeyValueStore(Protocol):
    """键值存储抽象"""

    def get(self, namespace: str, key: str) -> Optional[str]:
        """获取值"""
        ...

    def set(self, namespace: str, key: str, value: str, ttl: int | None = None) -> None:
        """设置值，可选 TTL（秒）"""
        ...

    def delete(self, namespace: str, key: str) -> None:
        """删除键"""
        ...

    def get_all(self, namespace: str) -> dict[str, str]:
        """获取命名空间下所有键值"""
        ...

    def clear(self, namespace: str) -> None:
        """清空命名空间"""
        ...
