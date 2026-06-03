"""
NLU 工具 — 意图解析、NLU 结果获取、急诊检测

职责: 理解用户输入的意图和实体。
"""
from __future__ import annotations

from agno.run import RunContext
from agno.tools import tool

from .nlu_context import get_nlu_context


@tool(stop_after_tool_call=False)
def agno_parse_nlu(text: str) -> dict:
    """解析用户输入，提取意图、实体和情绪。用于理解用户想做什么。"""
    from ..nlu_engine import nlu_engine
    result = nlu_engine.parse(text)
    return {
        "intent": result.intent,
        "entities": result.entities,
        "emotion": result.emotion,
        "is_emergency": result.is_emergency,
    }


@tool
def agno_get_nlu_result(run_context: RunContext | None = None) -> dict:
    """获取当前消息的已解析 NLU 结果（意图、实体、情绪）。
    结果由系统在路由阶段预计算并注入，无需再次解析。"""
    if run_context is not None and hasattr(run_context, "session_state"):
        nlu = run_context.session_state.get("nlu_result")
        if nlu:
            return nlu
    if run_context is not None and hasattr(run_context, "session_id"):
        nlu = get_nlu_context(run_context.session_id)
        if nlu:
            return nlu
    return {
        "intent": "UNKNOWN",
        "entities": {},
        "emotion": {"level": "neutral", "score": 0},
        "is_emergency": False,
        "note": "NLU结果未注入，使用默认值",
    }


@tool(stop_after_tool_call=True)
def agno_check_emergency(text: str) -> dict:
    """紧急情况检测 - 检查用户消息是否包含紧急医疗状况。
    如果检测到紧急情况，应立即引导就医，不再继续对话。"""
    from ..nlu_engine import nlu_engine
    result = nlu_engine.parse(text)
    if not result.is_emergency:
        return {"is_emergency": False, "message": ""}

    if result.intent == "SUICIDE_RISK":
        return {
            "is_emergency": True,
            "intent": "SUICIDE_RISK",
            "message": "⚠️ 我们非常关心您的安全。请立即拨打心理援助热线：400-161-9995，或前往最近医院急诊科寻求帮助。您不是一个人在面对困难。",
        }
    return {
        "is_emergency": True,
        "intent": result.intent,
        "message": "⚠️ 您描述的情况需要立即就医！请立刻联系您的医生或前往最近医院。如果情况紧急，请拨打120急救电话！",
    }
