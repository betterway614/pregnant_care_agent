"""对话记忆管理 - 短期记忆 + 云端状态键值对

重构: 支持注入 KeyValueStore 接口（OCP/DIP 合规），
同时保留旧的 redis_client 参数（向后兼容）。
"""
from typing import Optional
from datetime import datetime, timedelta
from ..utils.timezone import beijing_now


class MemoryManager:
    """对话记忆管理器

    支持三种存储后端（按优先级）:
    1. store: KeyValueStore 接口实现（推荐，DIP 合规）
    2. redis_client: Redis 客户端（向后兼容）
    3. 内存字典（开发环境兜底）

    - 存储功能性状态键值对（如 last_weight_date, last_reminder_id）
    - 不存储对话原文
    - 支持清除全部记忆
    """

    def __init__(self, redis_client=None, store=None):
        """
        Args:
            redis_client: Redis 客户端（向后兼容）
            store: KeyValueStore 接口实现（推荐）
        """
        self._store = store  # 优先使用 KeyValueStore
        self._redis = redis_client
        self._memory_store: dict[str, dict[str, str]] = {}
        self._ttl = timedelta(days=30)

    def _get_store(self, patient_id: str) -> dict[str, str]:
        """获取用户的记忆存储"""
        namespace = f"memory:{patient_id}"

        # 优先使用 KeyValueStore
        if self._store is not None:
            return self._store.get_all(namespace)

        # 回退到 Redis
        if self._redis:
            data = self._redis.hgetall(namespace)
            return {
                k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()
            }

        # 兜底：内存存储
        if patient_id not in self._memory_store:
            self._memory_store[patient_id] = {}
        return self._memory_store[patient_id]

    def _set_store(self, patient_id: str, store: dict[str, str]):
        """写入用户的记忆存储"""
        namespace = f"memory:{patient_id}"

        # 优先使用 KeyValueStore
        if self._store is not None:
            if store:
                for k, v in store.items():
                    self._store.set(namespace, k, v, ttl=int(self._ttl.total_seconds()))
            else:
                self._store.clear(namespace)
            return

        # 回退到 Redis
        if self._redis:
            if store:
                self._redis.hset(namespace, mapping=store)
                self._redis.expire(namespace, int(self._ttl.total_seconds()))
            else:
                self._redis.delete(namespace)
            return

        # 兜底：内存存储
        if store:
            self._memory_store[patient_id] = store
        elif patient_id in self._memory_store:
            del self._memory_store[patient_id]

    def get(self, patient_id: str, key: str) -> Optional[str]:
        """获取某条记忆"""
        store = self._get_store(patient_id)
        return store.get(key)

    def set(self, patient_id: str, key: str, value: str):
        """设置记忆键值对"""
        store = self._get_store(patient_id)
        store[key] = value
        self._set_store(patient_id, store)

    def set_multi(self, patient_id: str, kv_pairs: list[tuple[str, str]]):
        """批量设置记忆"""
        store = self._get_store(patient_id)
        for key, value in kv_pairs:
            store[key] = value
        self._set_store(patient_id, store)

    def clear(self, patient_id: str):
        """清除用户全部记忆"""
        self._set_store(patient_id, {})

    def get_all(self, patient_id: str) -> dict[str, str]:
        """获取全部记忆"""
        return dict(self._get_store(patient_id))

    def should_ask_weight(self, patient_id: str) -> bool:
        """检查今天是否已记录体重"""
        last_date = self.get(patient_id, "last_weight_date")
        if not last_date:
            return True
        try:
            last = datetime.strptime(last_date, "%Y-%m-%d").date()
            return last < beijing_now().date()
        except ValueError:
            return True

    def should_ask_bp(self, patient_id: str) -> bool:
        """检查今天是否已记录血压"""
        last_date = self.get(patient_id, "last_bp_date")
        if not last_date:
            return True
        try:
            last = datetime.strptime(last_date, "%Y-%m-%d").date()
            return last < beijing_now().date()
        except ValueError:
            return True


def _create_memory_manager() -> MemoryManager:
    """工厂函数：尝试从 DI 容器获取 KeyValueStore，回退到旧模式"""
    try:
        from ..container import container
        from ..interfaces.storage import KeyValueStore
        store = container.resolve(KeyValueStore)
        return MemoryManager(store=store)
    except Exception:
        pass

    # 回退：尝试 Redis
    try:
        from ..config import settings
        if settings.redis_url:
            import redis
            client = redis.from_url(settings.redis_url, decode_responses=True)
            return MemoryManager(redis_client=client)
    except Exception:
        pass

    # 兜底：纯内存
    return MemoryManager()


# 全局单例（尝试使用 DI 容器）
memory_manager = _create_memory_manager()
