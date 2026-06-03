"""
服务接口层 — 依赖倒置原则 (DIP) 的基础

所有接口使用 Python Protocol（结构化子类型），
实现类无需继承，只需方法签名匹配即可。
"""
from .repositories import PatientRepository, AlertRepository, FollowUpRepository
from .storage import KeyValueStore
from .notification import NotificationService
from .asr_backend import ASRBackend
from .tts_backend import TTSBackend

__all__ = [
    "PatientRepository", "AlertRepository", "FollowUpRepository",
    "KeyValueStore", "NotificationService",
    "ASRBackend", "TTSBackend",
]
