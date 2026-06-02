"""Agent 审计日志查询 API"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import AgentAuditLog
from ..core.auth import get_current_user, TokenPayload
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["审计日志"])


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


@router.get("/audit/sessions/{session_id}")
def get_session_audit(session_id: str, user: TokenPayload = Depends(get_current_user), db: Session = Depends(get_db)):
    """单次会话完整审计链"""
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
                "model_id": log.model_id,
                "total_latency_ms": log.total_latency_ms,
                "guardrail_triggered": log.guardrail_triggered,
                "response_preview": log.response_preview,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
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
                "guardrail_triggered": log.guardrail_triggered,
                "response_preview": log.response_preview,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in rows
        ],
    }


@router.get("/audit/dashboard")
def get_audit_dashboard(
    date_from: str = Query(..., description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(..., description="结束日期 YYYY-MM-DD"),
    user: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """仪表盘概览：汇总卡片 + 日趋势 + 变体分布 + 最近记录"""
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
        )
        .filter(AgentAuditLog.created_at >= dt_from, AgentAuditLog.created_at < dt_to)
        .first()
    )

    daily_trend = (
        db.query(
            func.date(AgentAuditLog.created_at).label("date"),
            func.sum(AgentAuditLog.total_tokens).label("total_tokens"),
            func.count(AgentAuditLog.id).label("call_count"),
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
        },
        "daily_trend": [
            {
                "date": str(row.date),
                "total_tokens": row.total_tokens or 0,
                "call_count": row.call_count,
            }
            for row in daily_trend
        ],
        "variant_distribution": [
            {
                "agent_variant": row.agent_variant,
                "count": row.count,
                "total_tokens": row.total_tokens or 0,
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
                "guardrail_triggered": log.guardrail_triggered,
                "response_preview": (log.response_preview or "")[:100],
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in recent_logs
        ],
    }
