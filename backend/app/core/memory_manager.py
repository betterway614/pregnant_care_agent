"""对话记忆管理 - 短期记忆 + 云端状态键值对"""
import time
from typing import Optional
from datetime import datetime, timedelta
from ..utils.timezone import beijing_now


class MemoryManager:
    """对话记忆管理器
    - 存储功能性状态键值对（如 last_weight_date, last_reminder_id）
    - 不存储对话原文
    - 支持清除全部记忆
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        # 本地内存后备存储（开发环境无Redis时使用）
        self._memory_store: dict[str, dict[str, str]] = {}
        self._ttl = timedelta(days=30)

    def _get_store(self, patient_id: str) -> dict[str, str]:
        """获取用户的记忆存储"""
        if self._redis:
            key = f"memory:{patient_id}"
            data = self._redis.hgetall(key)
            return {k.decode() if isinstance(k, bytes) else k:
                    v.decode() if isinstance(v, bytes) else v
                    for k, v in data.items()}
        if patient_id not in self._memory_store:
            self._memory_store[patient_id] = {}
        return self._memory_store[patient_id]

    def _set_store(self, patient_id: str, store: dict[str, str]):
        """写入用户的记忆存储"""
        if self._redis:
            key = f"memory:{patient_id}"
            if store:
                self._redis.hset(key, mapping=store)
                self._redis.expire(key, int(self._ttl.total_seconds()))
            else:
                self._redis.delete(key)
        else:
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


# 全局单例
memory_manager = MemoryManager()
