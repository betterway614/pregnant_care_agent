"""统一审计日志写入服务

消除 _save_audit_log / _save_nurse_audit_log / _save_doctor_audit_log /
_quick_audit / _alert_quick_audit 五份重复代码。
"""
from __future__ import annotations

import json as _json
import time as _time
from typing import Any

from loguru import logger

from ..database import SessionLocal
from ..models import AgentAuditLog, ToolCallDetail
from ..config import settings
from ..utils.timezone import beijing_now

# routed_agent 前缀映射
_ROUTED_AGENT_PREFIX: dict[str, str] = {
    "pregnant": "小安",
    "nurse": "小护",
    "doctor": "智医",
}


def _resolve_model_id_for_role(agent_role: str) -> str:
    """从配置获取角色对应的模型 ID 作为兜底"""
    try:
        from ..core.agno_client import _resolve_model_id
        role = agent_role if agent_role in ("pregnant", "nurse", "doctor") else "pregnant"
        return _resolve_model_id(role)  # type: ignore[arg-type]
    except Exception:
        return "unknown"


def _detect_tool_error(tc_result: Any) -> tuple[bool, str | None]:
    """鲁棒的工具调用错误检测

    支持 5 种错误模式：
    1. 显式 "error" key
    2. status == "error" / "failed"
    3. success == False
    4. 非零 error_code
    5. 字符串结果中包含 "error"/"exception"（警告但不算失败）
    """
    if not isinstance(tc_result, dict):
        return True, None
    # 模式 1: 显式 error key
    if "error" in tc_result and tc_result["error"]:
        return False, str(tc_result["error"])[:500]
    # 模式 2: status = "error" / "failed"
    status = tc_result.get("status", "")
    if isinstance(status, str) and status.lower() in ("error", "failed"):
        msg = tc_result.get("message", tc_result.get("reason", "Unknown error"))
        return False, str(msg)[:500]
    # 模式 3: success: false
    if tc_result.get("success") is False:
        msg = tc_result.get("message", tc_result.get("reason", "Tool returned failure"))
        return False, str(msg)[:500]
    # 模式 4: error_code 非零
    ec = tc_result.get("error_code")
    if ec is not None and ec != 0:
        msg = tc_result.get("message", f"Error code {ec}")
        return False, str(msg)[:500]
    return True, None


def _desensitize_health(text: str) -> str:
    """对健康数据与个人信息进行脱敏处理，替换数值为占位符。

    覆盖范围:
    - 健康指标: 血压/体重/血糖/心率/体温
    - 个人信息: 手机号
    """
    import re
    if not text:
        return text

    # ── 个人信息 ──
    # 中国大陆手机号: 1[3-9]xxxxxxxxx
    text = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', r'[手机号]', text)

    # ── 健康指标 ──
    # 血压: 覆盖 90-250/40-150 → [血压值]
    text = re.sub(
        r'(?<!\d)(0?[1-9]\d|[12][0-5]\d)\s*[/／]\s*(\d{2,3})\s*(?:mmHg|毫米汞柱)?\b',
        r'[血压值]', text
    )
    # 体重: 含单位的体重值 → [体重值]
    text = re.sub(
        r'(?<!\d)(\d{1,3}(?:\.\d)?)\s*(kg|公斤|斤|千克)\b',
        r'[体重值]', text
    )
    # 血糖: mmol/L 或 mg/dL → [血糖值]
    text = re.sub(
        r'(?<!\d)(\d{1,3}(?:\.\d)?)\s*(?:mmol/L|mmol/l|mg/dL|mg/dl)\b',
        r'[血糖值]', text
    )
    # 心率/胎心率: bpm → [心率值]
    text = re.sub(
        r'(?<!\d)(\d{2,3})\s*(?:bpm|次/分|次/分钟)\b',
        r'[心率值]', text
    )
    # 体温: ℃ → [体温值]
    text = re.sub(
        r'(?<!\d)(3[6-9]|40)(?:\.\d)?\s*[℃°C](?=\s|$|[^a-zA-Z])',
        r'[体温值]', text
    )
    return text


class AuditService:
    """统一审计日志写入服务"""

    @staticmethod
    def save_log(
        session_id: str,
        user_id: str,
        agent_role: str,
        agent_variant: str,
        intent_classification: str | None,
        user_message: str | None,
        run_response: Any,
        total_latency_ms: int,
        *,
        guardrail_triggered: bool = False,
        include_tool_details: bool = True,
        nlu_detail: dict | None = None,
        operator_id: str | None = None,
    ) -> int | None:
        """写入一条 AgentAuditLog（+ 可选 ToolCallDetail）

        Args:
            session_id: 会话 ID
            user_id: 被操作对象 ID（如孕妇 ID）
            agent_role: pregnant | nurse | doctor
            agent_variant: chat | analyze | workflow | ...
            intent_classification: NLU 意图
            user_message: 用户输入消息预览（脱敏，前 500 字）
            run_response: Agno Agent 的 RunResponse 对象
            total_latency_ms: 总延迟 ms
            guardrail_triggered: 安全护栏是否触发
            include_tool_details: 是否写入 ToolCallDetail 子表
            nlu_detail: NLU 完整解析结果
            operator_id: 操作者 ID（护士/医生端使用）

        Returns:
            审计日志 ID，失败/被过滤返回 None
        """
        # ── 审计总开关 ──
        if not getattr(settings, "audit_enabled", True):
            return None

        # ── 无效日志过滤：延迟 <10ms 且无 token 消耗 ──
        if total_latency_ms < 10:
            metrics = getattr(run_response, "metrics", None) if run_response else None
            input_tok = getattr(metrics, "input_tokens", None) if metrics else None
            output_tok = getattr(metrics, "output_tokens", None) if metrics else None
            if (input_tok is None or input_tok == 0) and (output_tok is None or output_tok == 0):
                logger.debug("跳过无效审计日志 session_id={} latency={}ms", session_id, total_latency_ms)
                return None

        # ── 重试写入（最多 2 次重试）──
        last_error = None
        for attempt in range(3):
            try:
                return AuditService._do_save(
                    session_id=session_id,
                    user_id=user_id,
                    agent_role=agent_role,
                    agent_variant=agent_variant,
                    intent_classification=intent_classification,
                    user_message=user_message,
                    run_response=run_response,
                    total_latency_ms=total_latency_ms,
                    guardrail_triggered=guardrail_triggered,
                    include_tool_details=include_tool_details,
                    nlu_detail=nlu_detail,
                    operator_id=operator_id,
                )
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    _time.sleep(0.1)  # 100ms 后重试
                else:
                    logger.warning(
                        "审计日志写入失败（重试 3 次后放弃）session_id={}: {}",
                        session_id, last_error,
                    )
        return None

    @staticmethod
    def _do_save(
        session_id: str,
        user_id: str,
        agent_role: str,
        agent_variant: str,
        intent_classification: str | None,
        user_message: str | None,
        run_response: Any,
        total_latency_ms: int,
        *,
        guardrail_triggered: bool,
        include_tool_details: bool,
        nlu_detail: dict | None,
        operator_id: str | None,
    ) -> int | None:
        """实际写入逻辑（无重试）"""
        # 守卫：流式异常时 run_response 可能为 None
        if run_response is None:
            run_response = type("_NullResponse", (), {
                "metrics": None, "content": "", "messages": [], "model": "",
            })()

        metrics = getattr(run_response, "metrics", None)
        content = getattr(run_response, "content", None)

        # ── 提取工具调用详情 ──
        tool_calls_legacy: list[dict] = []
        tool_call_details: list[ToolCallDetail] = []
        call_order = 0

        if include_tool_details and hasattr(run_response, "messages") and run_response.messages:
            for msg in run_response.messages:
                if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                    continue
                for tc in msg.tool_calls:
                    call_order += 1
                    tool_name = (
                        getattr(tc, "name", "")
                        or getattr(tc, "function", {}).get("name", "")
                    )

                    # 提取并脱敏工具入参
                    tool_args = None
                    raw_args = (
                        getattr(tc, "arguments", None)
                        or getattr(tc, "function", {}).get("arguments", None)
                    )
                    if raw_args is not None:
                        if isinstance(raw_args, str):
                            # 内存安全：超过 5000 字符直接截断
                            if len(raw_args) > 5000:
                                tool_args = {"_truncated": raw_args[:5000]}
                            else:
                                try:
                                    tool_args = _json.loads(raw_args)
                                except Exception:
                                    tool_args = {"_raw": raw_args[:500]}
                        elif isinstance(raw_args, dict):
                            tool_args = raw_args
                        # 脱敏：截断过长值
                        if tool_args and isinstance(tool_args, dict):
                            tool_args = {
                                k: (str(v)[:200] if isinstance(v, str) and len(v) > 200 else v)
                                for k, v in tool_args.items()
                            }

                    # 提取工具返回值
                    tc_result = getattr(tc, "result", None) or getattr(tc, "output", None)
                    result_preview = None
                    error_message = None
                    success = True
                    if tc_result is not None:
                        result_str = str(tc_result)
                        result_preview = result_str[:200] if result_str else None
                        success, error_message = _detect_tool_error(tc_result)

                    tool_calls_legacy.append({"name": tool_name, "success": success})
                    tool_call_details.append(ToolCallDetail(
                        tool_name=tool_name,
                        tool_args_json=tool_args,
                        success=success,
                        error_message=error_message,
                        latency_ms=None,
                        result_preview=result_preview,
                        call_order=call_order,
                    ))

        # ── 解析模型信息 ──
        model_id = ""
        provider = ""
        if metrics and hasattr(metrics, "details") and metrics.details:
            for _model_type, model_metrics_list in metrics.details.items():
                for m in model_metrics_list:
                    mid = getattr(m, "id", "")
                    if mid:
                        model_id = mid
                    prv = getattr(m, "provider", "")
                    if prv:
                        provider = prv
        if not model_id and hasattr(run_response, "model"):
            model_id = run_response.model or ""
        if not model_id:
            model_id = _resolve_model_id_for_role(agent_role)

        # ── Token 计数校验 ──
        input_tok = getattr(metrics, "input_tokens", 0) if metrics else 0
        output_tok = getattr(metrics, "output_tokens", 0) if metrics else 0
        total_tok = getattr(metrics, "total_tokens", 0) if metrics else 0
        # 如果 total 小于 input+output（provider 可能只返回了部分），用和替代
        if total_tok < (input_tok or 0) + (output_tok or 0):
            total_tok = (input_tok or 0) + (output_tok or 0)

        tool_error_count = sum(1 for d in tool_call_details if not d.success)

        # ── 敏感数据脱敏 ──
        raw_preview = content if isinstance(content, str) else ""
        response_preview = _desensitize_health(raw_preview[:200]) if raw_preview else None
        user_msg_preview = _desensitize_health(user_message[:500]) if user_message else None

        # ── routed_agent 前缀 ──
        prefix = _ROUTED_AGENT_PREFIX.get(agent_role, agent_role)
        routed_agent = f"{prefix}-{agent_variant}"

        # ── 写入数据库 ──
        db = SessionLocal()
        try:
            log_entry = AgentAuditLog(
                session_id=session_id,
                user_id=operator_id or user_id,
                agent_role=agent_role,
                agent_variant=agent_variant,
                intent_classification=intent_classification,
                routed_agent=routed_agent,
                input_tokens=input_tok or 0,
                output_tokens=output_tok or 0,
                total_tokens=total_tok or 0,
                tool_calls_json=tool_calls_legacy if tool_calls_legacy else None,
                tool_call_count=len(tool_calls_legacy),
                tool_error_count=tool_error_count,
                model_id=model_id or "unknown",
                provider=provider or "openai",
                total_latency_ms=total_latency_ms,
                guardrail_triggered=guardrail_triggered,
                response_preview=response_preview,
                user_message_preview=user_msg_preview,
                nlu_detail_json=nlu_detail,
            )
            db.add(log_entry)
            db.flush()

            for detail in tool_call_details:
                detail.audit_log_id = log_entry.id
                db.add(detail)

            db.commit()
            return log_entry.id
        except Exception:
            db.rollback()
            raise  # 抛给外层重试
        finally:
            db.close()
