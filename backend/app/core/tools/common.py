"""工具通用辅助函数"""
from __future__ import annotations

from agno.run import RunContext


def _resolve_pid(pregnant_id: str, run_context: RunContext | None) -> str:
    """解析孕妇ID：优先使用传入值，为空时从 RunContext.user_id 获取"""
    if pregnant_id:
        return pregnant_id
    if run_context is not None and hasattr(run_context, "user_id") and run_context.user_id:
        return run_context.user_id
    return ""
