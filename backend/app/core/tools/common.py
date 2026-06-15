"""工具通用辅助函数"""
from __future__ import annotations

import json

from agno.run import RunContext

# 工具返回结果最大字符数，防止对话历史上下文膨胀导致 LLM prefill 延迟
TOOL_RESULT_MAX_CHARS = 1500


def _resolve_pid(pregnant_id: str, run_context: RunContext | None) -> str:
    """解析孕妇ID：优先使用传入值，为空时从 RunContext.user_id 获取"""
    if pregnant_id:
        return pregnant_id
    if run_context is not None and hasattr(run_context, "user_id") and run_context.user_id:
        return run_context.user_id
    return ""


def truncate_tool_result(result: dict | str, max_chars: int = TOOL_RESULT_MAX_CHARS) -> str:
    """截断工具返回结果，防止对话历史上下文膨胀。

    本地 LLM (llama.cpp) 的 prefill 延迟与 context 长度正相关。
    工具结果会被完整存入对话历史（tool message），多轮调用后
    未截断的 JSON 会导致 context 膨胀到数千 tokens，首次响应
    延迟从 ~2s 劣化到 10s+。

    Args:
        result: 工具返回的 dict 或 str
        max_chars: 最大字符数（默认 1500，约 400 tokens）

    Returns:
        截断后的 JSON 字符串（始终保证 JSON 合法）
    """
    if isinstance(result, str):
        text = result
    else:
        text = str(result)
    if len(text) <= max_chars:
        return text
    # 截断后保证 JSON 合法：回退到 {"truncated": "...", "original_chars": N}
    try:
        preview = text[:max_chars]
        return json.dumps(
            {"truncated": preview, "original_chars": len(text)},
            ensure_ascii=False,
        )
    except Exception:
        return text[:max_chars]
