"""工具通用辅助函数"""
from __future__ import annotations

import json
import time
import threading
from typing import Optional

from agno.run import RunContext

# ==================== 分层截断阈值 ====================
# 按工具输出类型分档，避免"一刀切"导致数据查询类截断关键字段或简单计算类浪费上下文

# 指南检索类 — 内容密度高，512 字符无法传达有效信息，放宽到 3000
TRUNC_KNOWLEDGE = 3000
# 数据查询类 — 含多维度患者数据（趋势+预警+FGR+检验），2000 字符保关键字段不被腰斩
TRUNC_DATA_QUERY = 2000
# 默认 — 简单计算/布尔检查等，500-800 足够
TRUNC_SIMPLE = 800
# 标准 — 通用截断上限
TRUNC_DEFAULT = 1500

# 工具名 → 截断阈值映射（按前缀匹配，支持模糊分组）
TOOL_TRUNCATION_MAP: dict[str, int] = {
    # 指南/知识检索
    "agno_query_clinical_guideline": TRUNC_KNOWLEDGE,
    "search_knowledge_base": TRUNC_KNOWLEDGE,
    # 数据查询（多维度，需要更多空间）
    "agno_query_patient_data": TRUNC_DATA_QUERY,
    "agno_analyze_patient_comprehensive": TRUNC_DATA_QUERY,
    "agno_get_patient_context": TRUNC_DATA_QUERY,
    "agno_analyze_health_trends": TRUNC_DATA_QUERY,
    "agno_evaluate_vital_rules": TRUNC_DATA_QUERY,
    "agno_list_patients": TRUNC_DATA_QUERY,
    "agno_recommend_followup_schedule": TRUNC_DATA_QUERY,
    # 简单计算/布尔检查 — 小阈值即可
    "agno_get_epds_result": TRUNC_SIMPLE,
    "agno_get_pending_prompts": TRUNC_SIMPLE,
    "agno_get_nlu_result": TRUNC_SIMPLE,
    "agno_check_emergency": TRUNC_SIMPLE,
}


def _resolve_truncation_limit(tool_name: str | None = None) -> int:
    """根据工具名解析截断阈值，未匹配时回退到 TRUNC_DEFAULT"""
    if tool_name and tool_name in TOOL_TRUNCATION_MAP:
        return TOOL_TRUNCATION_MAP[tool_name]
    return TRUNC_DEFAULT


# ==================== 工具调用指标（轻量级，进程内存） ====================

class ToolMetrics:
    """工具调用指标收集器（线程安全，内存存储 + 可持久化到审计日志）

    双层追踪:
    1. 全局累计 — 进程级聚合，用于长期趋势分析
    2. Per-session 增量 — 每次 Agent 运行的工具调用详情，随审计日志持久化

    用法:
        metrics = tool_metrics
        metrics.start_session()                    # Agent 运行前
        metrics.record("agno_query", 45.2)         # 每次工具调用
        ...
        snap = metrics.end_session()               # Agent 运行后，返回增量快照
        AuditService.save_log(..., tool_metrics_snapshot=snap)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._global: dict[str, dict] = {}  # tool_name → {count, total_ms, last_called}
        self._session_start: dict[str, dict] | None = None  # 当前 session 的起始快照

    # ── 全局累计 ──

    def record(self, tool_name: str, duration_ms: float):
        """记录一次工具调用"""
        with self._lock:
            if tool_name not in self._global:
                self._global[tool_name] = {"count": 0, "total_ms": 0.0, "last_called": ""}
            m = self._global[tool_name]
            m["count"] += 1
            m["total_ms"] += duration_ms
            m["last_called"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

    def snapshot(self) -> dict:
        """获取全局累计指标快照"""
        with self._lock:
            return self._build_snapshot(self._global)

    def get_zero_usage_tools(self, known_tools: list[str]) -> list[str]:
        """返回已知但从未被调用的工具列表"""
        with self._lock:
            return [t for t in known_tools if t not in self._global]

    # ── Per-session 增量追踪 ──

    def start_session(self):
        """标记一个 Agent session 的开始，记录起始快照"""
        with self._lock:
            self._session_start = {
                name: dict(m) for name, m in self._global.items()
            }

    def end_session(self) -> dict | None:
        """结束 session，返回本次 session 的增量指标快照

        Returns:
            {
                "tools": {tool_name: {call_count, total_ms, avg_ms}, ...},
                "total_tool_calls": N,
                "total_tool_ms": M,
            }
            无数据时返回 None
        """
        with self._lock:
            if self._session_start is None:
                return None

            delta = {}
            total_calls = 0
            total_ms = 0.0

            for name, m in self._global.items():
                prev = self._session_start.get(name, {"count": 0, "total_ms": 0.0})
                d_count = m["count"] - prev["count"]
                d_ms = m["total_ms"] - prev["total_ms"]
                if d_count > 0:
                    delta[name] = {
                        "call_count": d_count,
                        "total_ms": round(d_ms, 1),
                        "avg_ms": round(d_ms / d_count, 1),
                    }
                    total_calls += d_count
                    total_ms += d_ms

            self._session_start = None

            if not delta:
                return None

            return {
                "tools": delta,
                "total_tool_calls": total_calls,
                "total_tool_ms": round(total_ms, 1),
            }

    # ── 内部 ──

    @staticmethod
    def _build_snapshot(metrics_dict: dict) -> dict:
        result = {}
        for name, m in metrics_dict.items():
            avg_ms = m["total_ms"] / m["count"] if m["count"] > 0 else 0
            result[name] = {
                "call_count": m["count"],
                "avg_duration_ms": round(avg_ms, 1),
                "last_called": m.get("last_called", ""),
            }
        return result


# 全局单例
tool_metrics = ToolMetrics()


# ==================== pid 解析 ====================


def _resolve_pid(pregnant_id: str, run_context: RunContext | None) -> str:
    """解析孕妇ID。

    护士/医生端如果路由层识别到本轮显式目标，会通过 session_state 注入
    explicit_patient_target_id。该目标优先级最高，用于抵御 LLM 工具参数误填
    或历史上下文串扰。
    """
    if run_context is not None and getattr(run_context, "session_state", None):
        explicit_pid = str(run_context.session_state.get("explicit_patient_target_id") or "").strip()
        if explicit_pid:
            if pregnant_id and pregnant_id != explicit_pid:
                run_context.session_state["target_mismatch_overridden"] = {
                    "requested": pregnant_id,
                    "used": explicit_pid,
                }
            return explicit_pid
    if pregnant_id:
        return pregnant_id
    if run_context is not None and hasattr(run_context, "user_id") and run_context.user_id:
        return run_context.user_id
    return ""


# ==================== 截断 ====================


def truncate_tool_result(
    result: dict | str,
    max_chars: int | None = None,
    tool_name: str | None = None,
    tool_start_time: float | None = None,
) -> str:
    """截断工具返回结果，防止对话历史上下文膨胀导致 LLM prefill 延迟。

    本地 LLM (llama.cpp) 的 prefill 延迟与 context 长度正相关。
    工具结果会被完整存入对话历史（tool message），多轮调用后
    未截断的 JSON 会导致 context 膨胀到数千 tokens，首次响应
    延迟从 ~2s 劣化到 10s+。

    同时记录工具调用指标到 tool_metrics（调用计数 + 可选耗时）。

    Args:
        result: 工具返回的 dict 或 str
        max_chars: 最大字符数（None 时根据 tool_name 自动选择阈值）
        tool_name: 工具名（用于匹配分层阈值 + 指标记录）
        tool_start_time: 工具开始时间（time.perf_counter()），用于精确耗时测量

    Returns:
        截断后的 JSON 字符串（始终保证 JSON 合法）
    """
    # ── 记录工具调用指标 ──
    if tool_name:
        duration_ms = 0.0
        if tool_start_time is not None:
            duration_ms = (time.perf_counter() - tool_start_time) * 1000
        tool_metrics.record(tool_name, duration_ms)

    if max_chars is None:
        max_chars = _resolve_truncation_limit(tool_name)

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


# ---- 带指标记录的工具调用包装器 ----

def wrap_tool_with_metrics(tool_name: str):
    """装饰器工厂：为工具函数添加调用指标记录

    用法:
        @wrap_tool_with_metrics("agno_query_patient_data")
        async def agno_query_patient_data(...):
            ...
    """
    def decorator(func):
        import functools

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                tool_metrics.record(tool_name, (time.perf_counter() - t0) * 1000)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                tool_metrics.record(tool_name, (time.perf_counter() - t0) * 1000)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
