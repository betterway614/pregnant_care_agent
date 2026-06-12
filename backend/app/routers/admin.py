"""Agent 审计日志查询 + API 配置管理 API"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Literal
from ..database import get_db
from ..models import AgentAuditLog, ToolCallDetail, Feedback
from ..config import settings
from ..core.auth import get_current_user, TokenPayload
import logging
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["审计日志"])


def _mask_api_key(key: str | None) -> str:
    """脱敏 API Key：仅显示后4位，其余用 * 替代。空值返回空字符串。"""
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


@router.get("/audit/token/daily")
def get_token_daily(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """日级别 token 消耗汇总"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

    rows = (
        db.query(
            func.date(AgentAuditLog.created_at).label("date"),
            func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
            func.sum(AgentAuditLog.input_tokens).label("input_tokens"),
            func.sum(AgentAuditLog.output_tokens).label("output_tokens"),
            func.count(AgentAuditLog.id).label("call_count"),
            func.avg(AgentAuditLog.total_latency_ms).label("avg_latency_ms"),
        )
        .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
        .group_by(func.date(AgentAuditLog.created_at))
        .order_by(func.date(AgentAuditLog.created_at))
        .all()
    )

    return {
        "data": [
            {
                "date": str(row.date),
                "total_tokens": row.total_tokens or 0,
                "input_tokens": row.input_tokens or 0,
                "output_tokens": row.output_tokens or 0,
                "call_count": row.call_count,
                "avg_latency_ms": round(row.avg_latency_ms or 0, 1),
            }
            for row in rows
        ]
    }


@router.get("/audit/token/by-agent")
def get_token_by_agent(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按智能体角色 + 变体汇总 token"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

    rows = (
        db.query(
            AgentAuditLog.agent_role,
            AgentAuditLog.agent_variant,
            func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
            func.count(AgentAuditLog.id).label("call_count"),
            func.avg(AgentAuditLog.input_tokens).label("avg_input_tokens"),
            func.avg(AgentAuditLog.output_tokens).label("avg_output_tokens"),
            func.avg(AgentAuditLog.total_latency_ms).label("avg_latency_ms"),
        )
        .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
        .group_by(AgentAuditLog.agent_role, AgentAuditLog.agent_variant)
        .order_by(AgentAuditLog.agent_role, func.sum(AgentAuditLog.total_tokens).desc())
        .all()
    )

    return {
        "data": [
            {
                "agent_role": row.agent_role,
                "agent_variant": row.agent_variant,
                "total_tokens": row.total_tokens or 0,
                "call_count": row.call_count,
                "avg_input_tokens": round(row.avg_input_tokens or 0, 1),
                "avg_output_tokens": round(row.avg_output_tokens or 0, 1),
                "avg_latency_ms": round(row.avg_latency_ms or 0, 1),
            }
            for row in rows
        ]
    }


@router.get("/audit/sessions")
def list_audit_sessions(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    user_id: str | None = Query(None, description="用户ID筛选"),
    agent_role: str | None = Query(None, description="角色筛选: pregnant|nurse|doctor"),
    agent_variant: str | None = Query(None, description="Agent变体筛选"),
    date_from: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分页查询审计会话列表"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    query = db.query(AgentAuditLog)

    if user_id:
        query = query.filter(AgentAuditLog.user_id == user_id)
    if agent_role:
        query = query.filter(AgentAuditLog.agent_role == agent_role)
    if agent_variant:
        query = query.filter(AgentAuditLog.agent_variant == agent_variant)
    if date_from:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        query = query.filter(AgentAuditLog.created_at >= dt_from)
    if date_to:
        dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(AgentAuditLog.created_at < dt_to)

    total = query.count()
    rows = (
        query.order_by(AgentAuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": [
            {
                "id": log.id,
                "session_id": log.session_id,
                "user_id": log.user_id,
                "agent_role": log.agent_role,
                "agent_variant": log.agent_variant,
                "intent_classification": log.intent_classification,
                "routed_agent": log.routed_agent,
                "input_tokens": log.input_tokens,
                "output_tokens": log.output_tokens,
                "total_tokens": log.total_tokens,
                "total_latency_ms": log.total_latency_ms,
                "llm_latency_ms": log.llm_latency_ms,
                "tool_call_count": log.tool_call_count or 0,
                "tool_error_count": log.tool_error_count or 0,
                "model_id": log.model_id,
                "guardrail_triggered": log.guardrail_triggered,
                "feedback_rating": log.feedback_rating,
                "response_preview": log.response_preview,
                "user_message_preview": log.user_message_preview,
                "nlu_detail_json": log.nlu_detail_json,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in rows
        ],
    }


@router.get("/audit/tool-calls/stats")
def get_tool_call_stats(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """工具调用统计：按工具名称聚合调用次数、成功率、平均耗时"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

    rows = (
        db.query(
            ToolCallDetail.tool_name,
            func.count(ToolCallDetail.id).label("call_count"),
            func.sum(func.cast(ToolCallDetail.success, db.bind.dialect.name == "postgresql" and func.cast or func.count)).label("success_count"),
            func.avg(ToolCallDetail.latency_ms).label("avg_latency_ms"),
        )
        .filter(ToolCallDetail.created_at >= dt_from, ToolCallDetail.created_at < dt_to)
        .group_by(ToolCallDetail.tool_name)
        .order_by(func.count(ToolCallDetail.id).desc())
        .all()
    )

    # 兼容 SQLite/PostgreSQL 的成功计数
    all_rows = (
        db.query(ToolCallDetail)
        .filter(ToolCallDetail.created_at >= dt_from, ToolCallDetail.created_at < dt_to)
        .all()
    )
    tool_stats: dict[str, dict] = {}
    for r in all_rows:
        name = r.tool_name
        if name not in tool_stats:
            tool_stats[name] = {"call_count": 0, "success_count": 0, "total_latency": 0, "latency_count": 0}
        tool_stats[name]["call_count"] += 1
        if r.success:
            tool_stats[name]["success_count"] += 1
        if r.latency_ms is not None:
            tool_stats[name]["total_latency"] += r.latency_ms
            tool_stats[name]["latency_count"] += 1

    return {
        "data": [
            {
                "tool_name": name,
                "call_count": s["call_count"],
                "success_count": s["success_count"],
                "error_count": s["call_count"] - s["success_count"],
                "success_rate": round(s["success_count"] / s["call_count"] * 100, 1) if s["call_count"] > 0 else 0,
                "avg_latency_ms": round(s["total_latency"] / s["latency_count"], 1) if s["latency_count"] > 0 else None,
            }
            for name, s in sorted(tool_stats.items(), key=lambda x: x[1]["call_count"], reverse=True)
        ]
    }


@router.get("/audit/tool-calls/errors")
def get_tool_call_errors(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
    tool_name: str | None = Query(None, description="工具名称筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """工具调用错误详情列表"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

    query = db.query(ToolCallDetail).filter(
        ToolCallDetail.created_at >= dt_from,
        ToolCallDetail.created_at < dt_to,
        ToolCallDetail.success == False,
    )
    if tool_name:
        query = query.filter(ToolCallDetail.tool_name == tool_name)

    total = query.count()
    rows = (
        query.order_by(ToolCallDetail.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": [
            {
                "id": r.id,
                "audit_log_id": r.audit_log_id,
                "tool_name": r.tool_name,
                "error_message": r.error_message,
                "tool_args": r.tool_args_json,
                "call_order": r.call_order,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/audit/feedback/summary")
def get_feedback_audit_summary(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """反馈 ↔ 审计关联统计：按 agent_variant 聚合满意度、工具调用次数、平均 token"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

    # 有反馈的审计日志
    logs_with_feedback = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.created_at >= dt_from,
            AgentAuditLog.created_at < dt_to,
            AgentAuditLog.feedback_rating.isnot(None),
        )
        .all()
    )

    # 按 variant 聚合
    variant_stats: dict[str, dict] = {}
    for log in logs_with_feedback:
        v = log.agent_variant
        if v not in variant_stats:
            variant_stats[v] = {
                "total_feedback": 0, "thumbs_up": 0, "thumbs_down": 0,
                "total_tool_calls": 0, "total_tokens": 0,
            }
        variant_stats[v]["total_feedback"] += 1
        if log.feedback_rating == "thumbs_up":
            variant_stats[v]["thumbs_up"] += 1
        else:
            variant_stats[v]["thumbs_down"] += 1
        variant_stats[v]["total_tool_calls"] += log.tool_call_count or 0
        variant_stats[v]["total_tokens"] += log.total_tokens or 0

    # 无反馈的审计日志统计
    total_logs = (
        db.query(func.count(AgentAuditLog.id))
        .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
        .scalar()
    )
    feedback_linked = len(logs_with_feedback)

    # 按角色聚合（从 Feedback 表直接查询）
    role_rows = (
        db.query(
            Feedback.feedback_role,
            func.count(Feedback.id).label("total"),
            func.sum(func.cast(Feedback.rating == "thumbs_up", db.bind.dialect.name == "postgresql" and func.cast or func.count)).label("up_count"),
        )
        .filter(Feedback.created_at >= dt_from, Feedback.created_at < dt_to)
        .group_by(Feedback.feedback_role)
        .all()
    )
    # 兼容 SQLite 的角色聚合
    all_feedbacks = (
        db.query(Feedback)
        .filter(Feedback.created_at >= dt_from, Feedback.created_at < dt_to)
        .all()
    )
    role_stats: dict[str, dict] = {}
    for fb in all_feedbacks:
        r = fb.feedback_role or "pregnant"
        if r not in role_stats:
            role_stats[r] = {"total": 0, "thumbs_up": 0, "thumbs_down": 0}
        role_stats[r]["total"] += 1
        if fb.rating == "thumbs_up":
            role_stats[r]["thumbs_up"] += 1
        else:
            role_stats[r]["thumbs_down"] += 1

    return {
        "feedback_coverage": {
            "total_audit_logs": total_logs or 0,
            "feedback_linked": feedback_linked,
            "coverage_rate": round(feedback_linked / total_logs * 100, 1) if total_logs else 0,
        },
        "by_variant": [
            {
                "agent_variant": v,
                "total_feedback": s["total_feedback"],
                "thumbs_up": s["thumbs_up"],
                "thumbs_down": s["thumbs_down"],
                "satisfaction_rate": round(s["thumbs_up"] / s["total_feedback"] * 100, 1) if s["total_feedback"] > 0 else 0,
                "avg_tool_calls": round(s["total_tool_calls"] / s["total_feedback"], 1) if s["total_feedback"] > 0 else 0,
                "avg_tokens": round(s["total_tokens"] / s["total_feedback"]) if s["total_feedback"] > 0 else 0,
            }
            for v, s in sorted(variant_stats.items(), key=lambda x: x[1]["total_feedback"], reverse=True)
        ],
        "by_role": [
            {
                "feedback_role": r,
                "total": s["total"],
                "thumbs_up": s["thumbs_up"],
                "thumbs_down": s["thumbs_down"],
                "satisfaction_rate": round(s["thumbs_up"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
            }
            for r, s in sorted(role_stats.items(), key=lambda x: x[1]["total"], reverse=True)
        ],
    }


@router.get("/audit/tool-calls/by-session/{session_id}")
def get_tool_calls_by_session(
    session_id: str,
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """单次会话的完整工具调用链"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    # 先获取该 session 的所有 audit_log IDs
    audit_logs = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.session_id == session_id)
        .order_by(AgentAuditLog.created_at)
        .all()
    )
    if not audit_logs:
        return {"session_id": session_id, "runs": []}

    audit_ids = [log.id for log in audit_logs]

    # 查询所有关联的工具调用详情
    tool_calls = (
        db.query(ToolCallDetail)
        .filter(ToolCallDetail.audit_log_id.in_(audit_ids))
        .order_by(ToolCallDetail.audit_log_id, ToolCallDetail.call_order)
        .all()
    )

    # 按 audit_log_id 分组
    tool_map: dict[int, list] = {}
    for tc in tool_calls:
        tool_map.setdefault(tc.audit_log_id, []).append(tc)

    return {
        "session_id": session_id,
        "runs": [
            {
                "audit_log_id": log.id,
                "agent_role": log.agent_role,
                "agent_variant": log.agent_variant,
                "intent": log.intent_classification,
                "tool_call_count": log.tool_call_count or 0,
                "tool_error_count": log.tool_error_count or 0,
                "total_tokens": log.total_tokens,
                "total_latency_ms": log.total_latency_ms,
                "llm_latency_ms": log.llm_latency_ms,
                "feedback_rating": log.feedback_rating,
                "tool_calls": [
                    {
                        "tool_name": tc.tool_name,
                        "success": tc.success,
                        "error_message": tc.error_message,
                        "tool_args": tc.tool_args_json,
                        "result_preview": tc.result_preview,
                        "call_order": tc.call_order,
                        "latency_ms": tc.latency_ms,
                    }
                    for tc in tool_map.get(log.id, [])
                ],
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in audit_logs
        ],
    }


@router.get("/audit/sessions/{session_id}")
def get_session_audit(session_id: str, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """单次会话完整审计链（增强版：含工具调用次数和反馈）"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    logs = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.session_id == session_id)
        .order_by(AgentAuditLog.created_at)
        .all()
    )

    return {
        "session_id": session_id,
        "run_count": len(logs),
        "total_tool_calls": sum(log.tool_call_count or 0 for log in logs),
        "total_tool_errors": sum(log.tool_error_count or 0 for log in logs),
        "runs": [
            {
                "id": log.id,
                "agent_role": log.agent_role,
                "agent_variant": log.agent_variant,
                "intent_classification": log.intent_classification,
                "routed_agent": log.routed_agent,
                "input_tokens": log.input_tokens,
                "output_tokens": log.output_tokens,
                "total_tokens": log.total_tokens,
                "tool_calls": log.tool_calls_json,
                "tool_call_count": log.tool_call_count or 0,
                "tool_error_count": log.tool_error_count or 0,
                "feedback_rating": log.feedback_rating,
                "feedback_comment": log.feedback_comment,
                "model_id": log.model_id,
                "total_latency_ms": log.total_latency_ms,
                "llm_latency_ms": log.llm_latency_ms,
                "guardrail_triggered": log.guardrail_triggered,
                "response_preview": log.response_preview,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


@router.get("/audit/dashboard")
def get_audit_dashboard(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """仪表盘概览（增强版）：汇总卡片 + 日趋势 + 变体分布 + 工具统计 + 反馈关联"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)

    summary_row = (
        db.query(
            func.count(AgentAuditLog.id).label("total_calls"),
            func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
            func.avg(AgentAuditLog.total_latency_ms).label("avg_latency_ms"),
            func.count(func.distinct(AgentAuditLog.session_id)).label("active_sessions"),
            func.sum(AgentAuditLog.tool_call_count).label("total_tool_calls"),
            func.sum(AgentAuditLog.tool_error_count).label("total_tool_errors"),
            func.count(AgentAuditLog.feedback_rating).label("feedback_count"),
        )
        .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
        .first()
    )

    daily_trend = (
        db.query(
            func.date(AgentAuditLog.created_at).label("date"),
            func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
            func.count(AgentAuditLog.id).label("call_count"),
            func.sum(AgentAuditLog.tool_call_count).label("tool_calls"),
        )
        .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
        .group_by(func.date(AgentAuditLog.created_at))
        .order_by(func.date(AgentAuditLog.created_at))
        .all()
    )

    variant_dist = (
        db.query(
            AgentAuditLog.agent_variant,
            func.count(AgentAuditLog.id).label("count"),
            func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
            func.sum(AgentAuditLog.tool_call_count).label("tool_calls"),
            func.sum(AgentAuditLog.tool_error_count).label("tool_errors"),
        )
        .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
        .group_by(AgentAuditLog.agent_variant)
        .all()
    )

    recent_logs = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
        .order_by(AgentAuditLog.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "summary": {
            "total_calls": summary_row.total_calls or 0,
            "total_tokens": summary_row.total_tokens or 0,
            "avg_latency_ms": round(summary_row.avg_latency_ms or 0, 1),
            "active_sessions": summary_row.active_sessions or 0,
            "total_tool_calls": summary_row.total_tool_calls or 0,
            "total_tool_errors": summary_row.total_tool_errors or 0,
            "tool_error_rate": round(
                (summary_row.total_tool_errors or 0) / (summary_row.total_tool_calls or 1) * 100, 1
            ),
            "feedback_count": summary_row.feedback_count or 0,
        },
        "daily_trend": [
            {
                "date": str(row.date),
                "total_tokens": row.total_tokens or 0,
                "call_count": row.call_count,
                "tool_calls": row.tool_calls or 0,
            }
            for row in daily_trend
        ],
        "variant_distribution": [
            {
                "agent_variant": row.agent_variant,
                "count": row.count,
                "total_tokens": row.total_tokens or 0,
                "tool_calls": row.tool_calls or 0,
                "tool_errors": row.tool_errors or 0,
            }
            for row in variant_dist
        ],
        "recent_logs": [
            {
                "id": log.id,
                "session_id": log.session_id,
                "user_id": log.user_id,
                "agent_variant": log.agent_variant,
                "intent_classification": log.intent_classification,
                "total_tokens": log.total_tokens,
                "total_latency_ms": log.total_latency_ms,
                "llm_latency_ms": log.llm_latency_ms,
                "tool_call_count": log.tool_call_count or 0,
                "tool_error_count": log.tool_error_count or 0,
                "guardrail_triggered": log.guardrail_triggered,
                "feedback_rating": log.feedback_rating,
                "response_preview": (log.response_preview or "")[:100],
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in recent_logs
        ],
    }


# ==================== API 配置管理 ====================

# 预定义云端供应商
CLOUD_PROVIDERS = [
    {
        "id": "dashscope",
        "name": "百炼平台 (DashScope)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "",
        "default_model": "qwen-plus",
        "available_models": [
            "qwen-plus",
            "qwen-turbo",
            "qwen-max",
            "qwen-long",
            "Qwen3.6-35B-A3B",
            "qwen-vl-max",
            "qwen-vl-plus",
        ],
        "description": "阿里云百炼平台，提供通义千问系列模型",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "default_model": "deepseek-chat",
        "available_models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "description": "DeepSeek 提供高性价比的推理模型",
    },
    {
        "id": "openai",
        "name": "OpenAI 兼容接口",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "default_model": "gpt-4o",
        "available_models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo",
        ],
        "description": "OpenAI 或兼容 OpenAI API 的第三方服务",
    },
]


class ApiConfigUpdate(BaseModel):
    # LLM 配置
    llm_mode: Optional[Literal["cloud", "local", "mock", "mixed"]] = None
    local_base_url: Optional[str] = None
    ollama_host: Optional[str] = None
    local_model: Optional[str] = None
    cloud_provider: Optional[str] = None
    cloud_api_key: Optional[str] = None
    cloud_base_url: Optional[str] = None
    cloud_model: Optional[str] = None
    cloud_vision_model: Optional[str] = None
    llm_pregnant_mode: Optional[str] = None
    llm_nurse_mode: Optional[str] = None
    llm_doctor_mode: Optional[str] = None
    llm_pregnant_model: Optional[str] = None
    llm_nurse_model: Optional[str] = None
    llm_doctor_model: Optional[str] = None
    # ASR 配置
    asr_mode: Optional[Literal["cloud", "local"]] = None
    asr_cloud_api_key: Optional[str] = None
    asr_cloud_base_url: Optional[str] = None
    asr_cloud_model: Optional[str] = None
    asr_local_backend: Optional[Literal["funasr", "whisper"]] = None
    asr_local_base_url: Optional[str] = None
    asr_local_model: Optional[str] = None
    asr_local_hotword: Optional[str] = None
    # TTS 配置
    tts_mode: Optional[Literal["browser", "cloud", "local"]] = None
    tts_cloud_api_key: Optional[str] = None
    tts_cloud_base_url: Optional[str] = None
    tts_cloud_model: Optional[str] = None
    tts_cloud_voice: Optional[str] = None
    tts_local_backend: Optional[Literal["edge", "cosyvoice"]] = None
    tts_local_cosyvoice_url: Optional[str] = None
    tts_local_cosyvoice_speaker: Optional[str] = None
    # Embedding 配置
    embedding_api_url: Optional[str] = None
    embedding_api_key: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimensions: Optional[int] = None


class ApiTestRequest(BaseModel):
    mode: Literal["local", "cloud"]
    provider: Optional[str] = None


def _detect_cloud_provider() -> str:
    """根据当前 base_url 推断当前使用的供应商"""
    base_url = settings.llm_base_url
    if "dashscope" in base_url or "aliyuncs" in base_url:
        return "dashscope"
    if "deepseek" in base_url:
        return "deepseek"
    if "openai" in base_url:
        return "openai"
    return "dashscope"


@router.get("/api-config")
def get_api_config(user: TokenPayload = Depends(get_current_user)):
    """获取当前 API 配置"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    current_provider = _detect_cloud_provider()

    # 填充当前 API key 到对应供应商
    providers = []
    for p in CLOUD_PROVIDERS:
        provider = {**p}
        if provider["id"] == current_provider:
            provider["api_key"] = _mask_api_key(settings.llm_api_key)
            provider["base_url"] = settings.llm_base_url
        providers.append(provider)

    return {
        "llm_mode": settings.llm_mode,
        "local_base_url": settings.local_base_url,
        "ollama_host": settings.ollama_host,
        "local_model": settings.local_model,
        "cloud_provider": current_provider,
        "cloud_api_key": _mask_api_key(settings.llm_api_key),
        "cloud_base_url": settings.llm_base_url,
        "cloud_model": settings.llm_model,
        "cloud_vision_model": settings.llm_vision_model,
        "available_providers": providers,
        "llm_pregnant_mode": settings.llm_pregnant_mode,
        "llm_nurse_mode": settings.llm_nurse_mode,
        "llm_doctor_mode": settings.llm_doctor_mode,
        "llm_pregnant_model": settings.llm_pregnant_model,
        "llm_nurse_model": settings.llm_nurse_model,
        "llm_doctor_model": settings.llm_doctor_model,
        # ASR 配置
        "asr_mode": settings.asr_mode,
        "asr_cloud_api_key": _mask_api_key(settings.asr_cloud_api_key),
        "asr_cloud_base_url": settings.asr_cloud_base_url,
        "asr_cloud_model": settings.asr_cloud_model,
        "asr_local_backend": settings.asr_local_backend,
        "asr_local_base_url": settings.asr_local_base_url,
        "asr_local_model": settings.asr_local_model,
        "asr_local_hotword": settings.asr_local_hotword,
        # TTS 配置
        "tts_mode": settings.tts_mode,
        "tts_cloud_api_key": _mask_api_key(settings.tts_cloud_api_key),
        "tts_cloud_base_url": settings.tts_cloud_base_url,
        "tts_cloud_model": settings.tts_cloud_model,
        "tts_cloud_voice": settings.tts_cloud_voice,
        "tts_local_backend": settings.tts_local_backend,
        "tts_local_cosyvoice_url": settings.tts_local_cosyvoice_url,
        "tts_local_cosyvoice_speaker": settings.tts_local_cosyvoice_speaker,
        # Embedding 配置
        "embedding_api_url": settings.embedding_api_url,
        "embedding_api_key": _mask_api_key(settings.embedding_api_key),
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
    }


@router.put("/api-config")
def update_api_config(
    body: ApiConfigUpdate,
    user: TokenPayload = Depends(get_current_user),
):
    """更新 API 配置（写入 .env 文件）"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    import os
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", ".env")
    env_path = os.path.normpath(env_path)

    # 读取现有 .env 内容
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            env_lines = f.readlines()

    # 构建 key -> line index 映射
    env_map: dict[str, int] = {}
    for i, line in enumerate(env_lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            env_map[key] = i

    # 字段到环境变量名的映射
    field_to_env = {
        "llm_mode": "LLM_MODE",
        "local_base_url": "LOCAL_BASE_URL",
        "ollama_host": "OLLAMA_HOST",
        "local_model": "LOCAL_MODEL",
        "cloud_api_key": "LLM_API_KEY",
        "cloud_base_url": "LLM_BASE_URL",
        "cloud_model": "LLM_MODEL",
        "cloud_vision_model": "LLM_VISION_MODEL",
        "llm_pregnant_mode": "LLM_PREGNANT_MODE",
        "llm_nurse_mode": "LLM_NURSE_MODE",
        "llm_doctor_mode": "LLM_DOCTOR_MODE",
        "llm_pregnant_model": "LLM_PREGNANT_MODEL",
        "llm_nurse_model": "LLM_NURSE_MODEL",
        "llm_doctor_model": "LLM_DOCTOR_MODEL",
        # ASR 配置
        "asr_mode": "ASR_MODE",
        "asr_cloud_api_key": "ASR_CLOUD_API_KEY",
        "asr_cloud_base_url": "ASR_CLOUD_BASE_URL",
        "asr_cloud_model": "ASR_CLOUD_MODEL",
        "asr_local_backend": "ASR_LOCAL_BACKEND",
        "asr_local_base_url": "ASR_LOCAL_BASE_URL",
        "asr_local_model": "ASR_LOCAL_MODEL",
        "asr_local_hotword": "ASR_LOCAL_HOTWORD",
        # TTS 配置
        "tts_mode": "TTS_MODE",
        "tts_cloud_api_key": "TTS_CLOUD_API_KEY",
        "tts_cloud_base_url": "TTS_CLOUD_BASE_URL",
        "tts_cloud_model": "TTS_CLOUD_MODEL",
        "tts_cloud_voice": "TTS_CLOUD_VOICE",
        "tts_local_backend": "TTS_LOCAL_BACKEND",
        "tts_local_cosyvoice_url": "TTS_LOCAL_COSYVOICE_URL",
        "tts_local_cosyvoice_speaker": "TTS_LOCAL_COSYVOICE_SPEAKER",
        # Embedding 配置
        "embedding_api_url": "EMBEDDING_API_URL",
        "embedding_api_key": "EMBEDDING_API_KEY",
        "embedding_model": "EMBEDDING_MODEL",
        "embedding_dimensions": "EMBEDDING_DIMENSIONS",
    }

    # 处理 cloud_provider 特殊逻辑
    updates = body.model_dump(exclude_none=True)
    if "cloud_provider" in updates:
        provider_id = updates.pop("cloud_provider")
        for p in CLOUD_PROVIDERS:
            if p["id"] == provider_id:
                # 如果 base_url 未显式指定，则使用供应商默认
                if "cloud_base_url" not in updates:
                    updates["cloud_base_url"] = p["base_url"]
                # 如果 model 未显式指定，则使用供应商默认
                if "cloud_model" not in updates:
                    updates["cloud_model"] = p["default_model"]
                break

    # 应用更新到内存配置 + .env 文件
    changed_keys = []
    for field, value in updates.items():
        env_key = field_to_env.get(field)
        if not env_key:
            continue

        # 跳过脱敏后的 API Key（含 ****），避免用脱敏值覆盖真实密钥
        if isinstance(value, str) and "****" in value:
            continue

        # 更新内存中的 settings
        if hasattr(settings, env_key.lower()):
            setattr(settings, env_key.lower(), value)

        # 更新 .env 文件
        new_line = f'{env_key}="{value}"\n'
        if env_key in env_map:
            env_lines[env_map[env_key]] = new_line
        else:
            env_lines.append(new_line)
        changed_keys.append(env_key)

    # 写回 .env
    if changed_keys:
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(env_lines)
        logger.info("API 配置已更新: %s", ", ".join(changed_keys))

    return {
        "message": "配置已保存，部分配置重启后生效",
        "config": get_api_config(user),
    }


@router.post("/api-config/test")
async def test_api_connection(
    body: ApiTestRequest,
    user: TokenPayload = Depends(get_current_user),
):
    """测试 API 连接"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    if body.mode == "local":
        base_url = settings.local_base_url or settings.ollama_host
        url = f"{base_url}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id", "") for m in data.get("data", [])]
                    return {
                        "success": True,
                        "message": f"连接成功，发现 {len(models)} 个模型",
                        "model": models[0] if models else None,
                    }
                return {
                    "success": False,
                    "message": f"连接失败: HTTP {resp.status_code}",
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
            }

    # 云端测试
    provider_id = body.provider or _detect_cloud_provider()
    provider = next((p for p in CLOUD_PROVIDERS if p["id"] == provider_id), None)
    if not provider:
        return {"success": False, "message": f"未知供应商: {provider_id}"}

    base_url = settings.llm_base_url
    api_key = settings.llm_api_key
    model = settings.llm_model

    if not api_key:
        return {"success": False, "message": "未配置 API Key"}

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5,
    }

    import time
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            latency = round((time.time() - start) * 1000)
            if resp.status_code == 200:
                return {
                    "success": True,
                    "message": "连接成功",
                    "latency_ms": latency,
                    "model": model,
                }
            error_detail = resp.text[:200]
            return {
                "success": False,
                "message": f"请求失败: HTTP {resp.status_code} - {error_detail}",
                "latency_ms": latency,
            }
    except Exception as e:
        latency = round((time.time() - start) * 1000)
        return {
            "success": False,
            "message": f"连接失败: {str(e)}",
            "latency_ms": latency,
        }


# ==================== 数据保留 ====================

@router.post("/audit/cleanup")
def cleanup_audit_logs(
    days: int = Query(90, description="保留最近 N 天的审计日志，默认 90 天"),
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """清理超过指定天数的审计日志和工具调用详情（需管理员权限）

    只清理旧数据，保留近期日志用于分析和审计追溯。
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    cutoff = datetime.now() - timedelta(days=max(days, 30))  # 至少保留 30 天
    deleted_logs = 0
    deleted_tools = 0

    try:
        # 先删子表（工具调用详情）
        old_log_ids = db.query(AgentAuditLog.id).filter(
            AgentAuditLog.created_at < cutoff
        ).subquery()
        deleted_tools = db.query(ToolCallDetail).filter(
            ToolCallDetail.audit_log_id.in_(old_log_ids)
        ).delete(synchronize_session=False)

        # 再删主表
        deleted_logs = db.query(AgentAuditLog).filter(
            AgentAuditLog.created_at < cutoff
        ).delete(synchronize_session=False)

        db.commit()
        logger.info("审计日志清理完成: 删除 %d 条日志, %d 条工具调用", deleted_logs, deleted_tools)

        return {
            "success": True,
            "cutoff": cutoff.isoformat(),
            "deleted_audit_logs": deleted_logs,
            "deleted_tool_calls": deleted_tools,
        }
    except Exception:
        db.rollback()
        raise HTTPException(500, "清理审计日志失败")


import os as _os
import signal as _signal
import subprocess as _subprocess
import threading as _threading
import time as _time

_BACKEND_DIR = _os.path.normpath(
    _os.path.join(_os.path.dirname(__file__), "..", "..")
)


@router.post("/system/restart")
def restart_system(user: TokenPayload = Depends(get_current_user)):
    """重启后端服务（仅重启 Python 进程以加载新的 .env 配置）

    不影响 frontend / Docker / AI 推理服务。
    响应返回后，子进程会在 1 秒延迟后：
      1. 发送 SIGTERM 给当前后端进程
      2. 等待端口释放
      3. 启动新的 python run.py
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    current_pid = _os.getpid()
    port = int(_os.environ.get("PORT", "9999"))

    def _do_restart() -> None:
        _time.sleep(1.0)  # 确保 HTTP 响应已发出

        # 1) 优雅终止当前进程
        try:
            _os.kill(current_pid, _signal.SIGTERM)
        except ProcessLookupError:
            pass

        # 2) 等待端口释放
        _time.sleep(2.0)
        deadline = _time.time() + 15
        while _time.time() < deadline:
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect(("127.0.0.1", port))
                s.close()
                _time.sleep(0.5)
            except (ConnectionRefusedError, OSError):
                break

        # 3) 启动新后端进程
        _subprocess.Popen(
            ["python", "run.py"],
            cwd=_BACKEND_DIR,
            start_new_session=True,
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
            env={**_os.environ, "PORT": str(port)},
        )

    _threading.Thread(target=_do_restart, daemon=True).start()
    logger.info("已调度后端重启 (PID: %s, 端口: %s)", current_pid, port)
    return {"message": "后端服务正在重启，请等待约 10 秒后刷新页面"}
