"""Agent 审计日志查询 + API 配置管理 API"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Literal
from ..database import get_db
from ..models import AgentAuditLog
from ..config import settings
from ..core.auth import get_current_user, TokenPayload
import logging
import httpx

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
            provider["api_key"] = settings.llm_api_key
            provider["base_url"] = settings.llm_base_url
        providers.append(provider)

    return {
        "llm_mode": settings.llm_mode,
        "local_base_url": settings.local_base_url or settings.ollama_host,
        "ollama_host": settings.ollama_host,
        "local_model": settings.local_model,
        "cloud_provider": current_provider,
        "cloud_api_key": settings.llm_api_key,
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

        # 更新内存中的 settings
        if hasattr(settings, env_key.lower()):
            setattr(settings, env_key.lower(), value)
        elif field == "cloud_api_key":
            settings.llm_api_key = value
        elif field == "cloud_base_url":
            settings.llm_base_url = value
        elif field == "cloud_model":
            settings.llm_model = value
        elif field == "cloud_vision_model":
            settings.llm_vision_model = value

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
        logger.info("API 配置已更新: {}", ", ".join(changed_keys))

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
