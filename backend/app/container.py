"""
轻量级依赖注入容器

设计理念:
- 使用 Python 模块级工厂函数（Python 惯用模式）
- 不引入第三方 DI 框架，保持简单
- 通过 Agent(dependencies={...}) 桥接到 Agno 的 RunContext
"""
from __future__ import annotations

from typing import Any, Callable, TypeVar
from loguru import logger

T = TypeVar("T")


class Container:
    """服务容器 — 管理服务实例的创建和生命周期"""

    def __init__(self) -> None:
        self._factories: dict[type, Callable] = {}
        self._singletons: dict[type, Any] = {}
        self._singleton_types: set[type] = set()
        self._initialized = False

    def register_factory(self, interface: type[T], factory: Callable[[], T]) -> None:
        """注册工厂函数（每次调用创建新实例）"""
        self._factories[interface] = factory

    def register_singleton(self, interface: type[T], factory: Callable[[], T]) -> None:
        """注册单例工厂（首次调用后缓存）"""
        self._factories[interface] = factory
        self._singleton_types.add(interface)

    def resolve(self, interface: type[T]) -> T:
        """解析服务实例"""
        if interface in self._singletons:
            return self._singletons[interface]
        if interface in self._factories:
            instance = self._factories[interface]()
            if interface in self._singleton_types:
                self._singletons[interface] = instance
            return instance
        raise ValueError(f"未注册的服务: {interface.__name__}")

    def initialize(self) -> None:
        """预初始化所有单例服务（应用启动时调用）"""
        if self._initialized:
            return
        for interface in self._singleton_types:
            self.resolve(interface)
        self._initialized = True
        logger.info("服务容器初始化完成，已注册 {} 个服务", len(self._factories))


# 全局容器实例
container = Container()


def setup_container() -> None:
    """配置所有服务绑定 — 应用启动时调用一次

    在 main.py 的 lifespan 中调用此函数完成服务注册。
    """
    from .interfaces.storage import KeyValueStore
    from .interfaces.notification import NotificationService
    from .interfaces.asr_backend import ASRBackend
    from .interfaces.tts_backend import TTSBackend
    from .config import settings

    # --- 键值存储 ---
    def make_kv_store() -> KeyValueStore:
        if settings.redis_url:
            from .services.redis_store import RedisKeyValueStore
            return RedisKeyValueStore(settings.redis_url)
        from .services.memory_store import InMemoryKeyValueStore
        return InMemoryKeyValueStore()

    # --- 通知服务 ---
    def make_notification_service() -> NotificationService:
        from .core.websocket_manager import ws_manager
        return ws_manager  # WebSocketManager 已实现协议方法

    # --- ASR 后端 ---
    def make_asr_backend() -> ASRBackend:
        mode = settings.asr_mode if hasattr(settings, "asr_mode") else "cloud"
        if mode == "cloud":
            from .services.asr_backends import DashScopeASRBackend
            return DashScopeASRBackend(getattr(settings, "asr_api_key", ""))
        elif mode == "local":
            backend = getattr(settings, "asr_local_backend", "funasr")
            if backend == "funasr":
                from .services.asr_backends import FunASRBackend
                return FunASRBackend(getattr(settings, "funasr_server_url", "http://localhost:10095"))
            else:
                from .services.asr_backends import WhisperBackend
                return WhisperBackend()
        from .services.asr_backends import MockASRBackend
        return MockASRBackend()

    # --- TTS 后端 ---
    def make_tts_backend() -> TTSBackend:
        mode = settings.tts_mode if hasattr(settings, "tts_mode") else "browser"
        if mode == "cloud":
            from .services.tts_backends import DashScopeTTSBackend
            return DashScopeTTSBackend(getattr(settings, "tts_api_key", ""))
        elif mode == "local":
            from .services.tts_backends import EdgeTTSBackend
            return EdgeTTSBackend()
        from .services.tts_backends import MockTTSBackend
        return MockTTSBackend()

    container.register_singleton(KeyValueStore, make_kv_store)
    container.register_singleton(NotificationService, make_notification_service)
    container.register_singleton(ASRBackend, make_asr_backend)
    container.register_singleton(TTSBackend, make_tts_backend)

    container.initialize()
