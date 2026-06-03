"""
NLU 上下文管理 — 线程安全的 NLU 结果缓存

职责: 在路由层预计算 NLU 结果后注入，供工具层读取。
使用带时间戳的结构，支持自动过期清理，防止内存泄漏。
"""
from __future__ import annotations

import threading
import time as _time

_nlu_context: dict[str, tuple[dict, float]] = {}
_nlu_context_lock = threading.Lock()
_NLU_CONTEXT_TTL = 600  # 10 分钟过期


def set_nlu_context(session_id: str, nlu_dict: dict) -> None:
    """线程安全地设置 NLU 上下文"""
    with _nlu_context_lock:
        _nlu_context[session_id] = (nlu_dict, _time.time())


def get_nlu_context(session_id: str) -> dict | None:
    """线程安全地获取 NLU 上下文，过期条目自动清理"""
    with _nlu_context_lock:
        entry = _nlu_context.get(session_id)
        if entry is None:
            return None
        nlu_dict, ts = entry
        if _time.time() - ts > _NLU_CONTEXT_TTL:
            del _nlu_context[session_id]
            return None
        return nlu_dict


def pop_nlu_context(session_id: str) -> dict | None:
    """线程安全地弹出 NLU 上下文"""
    with _nlu_context_lock:
        entry = _nlu_context.pop(session_id, None)
        if entry is None:
            return None
        nlu_dict, ts = entry
        return nlu_dict


def cleanup_expired_nlu_context() -> int:
    """清理所有过期的 NLU 上下文条目，返回清理数量"""
    now = _time.time()
    with _nlu_context_lock:
        expired = [k for k, (_, ts) in _nlu_context.items() if now - ts > _NLU_CONTEXT_TTL]
        for k in expired:
            del _nlu_context[k]
        return len(expired)
