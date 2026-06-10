"""系统资源管理 API - 服务配置、监控策略、优化建议"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from ..core.auth import get_current_user, TokenPayload
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/resource", tags=["资源管理"])


# ==================== Pydantic 模型 ====================


class ServiceConfigUpdate(BaseModel):
    """服务配置更新请求"""
    batch_size: Optional[int] = None
    accelerator: Optional[str] = None
    priority: Optional[int] = None


class PolicyUpdate(BaseModel):
    """策略切换请求"""
    policy: str
    reason: Optional[str] = None


class MonitoringControl(BaseModel):
    """监控控制请求"""
    interval: float = 5.0


# ==================== 依赖 ====================


def _require_admin(user: TokenPayload):
    """统一管理员权限校验"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")


# ==================== 端点 ====================


@router.get("/status")
def get_system_status(user: TokenPayload = Depends(get_current_user)):
    """获取系统资源状态（VRAM、GPU、CPU、NPU）"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    return resource_service.get_system_status()


@router.get("/services")
def get_service_configs(user: TokenPayload = Depends(get_current_user)):
    """获取所有服务配置"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    return resource_service.get_service_configs()


@router.put("/services/{service_name}")
def update_service_config(
    service_name: str,
    body: ServiceConfigUpdate,
    user: TokenPayload = Depends(get_current_user),
):
    """更新指定服务的配置"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(status_code=400, detail="未提供任何更新字段")

    success = resource_service.update_service_config(service_name, **kwargs)
    if not success:
        raise HTTPException(status_code=404, detail=f"服务 {service_name} 不存在或更新失败")

    logger.info("管理员 %s 更新服务 %s 配置: %s", user.sub, service_name, kwargs)
    return {"message": f"服务 {service_name} 配置已更新", "config": kwargs}


@router.get("/policy")
def get_policy(user: TokenPayload = Depends(get_current_user)):
    """获取当前资源调度策略"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    status = resource_service.get_system_status()
    return status.get("policy", {})


@router.put("/policy")
def set_policy(
    body: PolicyUpdate,
    user: TokenPayload = Depends(get_current_user),
):
    """切换资源调度策略"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    success = resource_service.set_policy(body.policy)
    if not success:
        raise HTTPException(status_code=400, detail=f"无效的策略名称: {body.policy}")

    logger.info("管理员 %s 切换策略为 %s", user.sub, body.policy)
    return {"message": f"策略已切换到 {body.policy}", "policy": body.policy}


@router.get("/adjustments")
def get_adjustments(user: TokenPayload = Depends(get_current_user)):
    """获取资源优化建议"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    return {"adjustments": resource_service.get_adjustments()}


@router.get("/history")
def get_history(
    limit: int = Query(100, ge=1, le=1000, description="返回记录数上限"),
    user: TokenPayload = Depends(get_current_user),
):
    """获取历史资源使用数据"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    return {"history": resource_service.get_history(limit=limit)}


@router.get("/services-health")
def get_services_health(user: TokenPayload = Depends(get_current_user)):
    """获取所有服务的健康状态（代理后端检测）

    解决 SSH 端口转发场景下前端无法直接访问 127.0.0.1:port 的问题。
    由后端直接检测各服务的健康状态，前端只调用本 API。
    """
    _require_admin(user)
    from ..core.resource_rules import resource_rule_engine
    from ..config import settings
    import requests

    services = ["llm", "bge_m3", "tts", "asr"]
    result = {}
    for name in services:
        config = resource_rule_engine.services.get(name)
        if not config:
            continue
        host = getattr(settings, f"resource_{name}_host", "127.0.0.1")
        port = config.port
        status = {"online": False, "model": "", "device": ""}
        try:
            # 优先查询 /device 端点（适用于 embedding server）
            resp = requests.get(f"http://{host}:{port}/device", timeout=1)
            if resp.ok:
                data = resp.json()
                status["online"] = True
                if data.get("model_loaded"):
                    status["model"] = name
                if data.get("device"):
                    status["device"] = data["device"]
                result[name] = status
                continue
        except Exception:
            pass
        try:
            # 回退到 /health 端点
            resp = requests.get(f"http://{host}:{port}/health", timeout=1)
            if resp.ok:
                data = resp.json()
                status["online"] = True
                if data.get("model_name"):
                    status["model"] = data["model_name"]
                if data.get("device"):
                    status["device"] = data["device"]
        except Exception:
            pass
        result[name] = status
    return {"services": result}


@router.post("/monitoring/start")
def start_monitoring(
    body: MonitoringControl = None,
    user: TokenPayload = Depends(get_current_user),
):
    """启动资源监控"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    interval = body.interval if body else 5.0
    resource_service.start_monitoring(interval=interval)

    logger.info("管理员 %s 启动资源监控 (间隔: %ss)", user.sub, interval)
    return {"message": f"资源监控已启动 (间隔: {interval}s)"}


@router.post("/monitoring/stop")
def stop_monitoring(user: TokenPayload = Depends(get_current_user)):
    """停止资源监控"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    resource_service.stop_monitoring()

    logger.info("管理员 %s 停止资源监控", user.sub)
    return {"message": "资源监控已停止"}


@router.get("/llm-analysis")
async def get_llm_analysis(
    type: str = Query("pattern", description="分析类型: pattern/anomaly/optimization/report"),
    user: TokenPayload = Depends(get_current_user),
):
    """获取 LLM 智能分析建议"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    result = await resource_service.get_llm_analysis(analysis_type=type)
    return result


# ==================== 资源预警 API ====================


@router.get("/alerts")
def get_resource_alerts(
    status: Optional[str] = Query(None, description="预警状态: active/acknowledged/resolved"),
    alert_type: Optional[str] = Query(None, description="预警类型"),
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
    user: TokenPayload = Depends(get_current_user),
):
    """获取资源预警列表"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import ResourceAlert

    db = SessionLocal()
    try:
        query = db.query(ResourceAlert)

        if status:
            query = query.filter(ResourceAlert.status == status)
        if alert_type:
            query = query.filter(ResourceAlert.alert_type == alert_type)

        alerts = query.order_by(ResourceAlert.created_at.desc()).limit(limit).all()

        return {
            "alerts": [
                {
                    "id": alert.id,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "title": alert.title,
                    "message": alert.message,
                    "vram_percent": alert.vram_percent,
                    "gpu_percent": alert.gpu_percent,
                    "cpu_percent": alert.cpu_percent,
                    "gpu_power_w": alert.gpu_power_w,
                    "gpu_temp_c": alert.gpu_temp_c,
                    "cpu_temp_c": alert.cpu_temp_c,
                    "status": alert.status,
                    "acknowledged_by": alert.acknowledged_by,
                    "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                    "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                    "resolution": alert.resolution,
                    "policy_name": alert.policy_name,
                    "auto_action": alert.auto_action,
                    "created_at": alert.created_at.isoformat() if alert.created_at else None,
                }
                for alert in alerts
            ]
        }
    finally:
        db.close()


@router.put("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    user: TokenPayload = Depends(get_current_user),
):
    """确认资源预警"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import ResourceAlert
    from datetime import datetime

    db = SessionLocal()
    try:
        alert = db.query(ResourceAlert).filter(ResourceAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="预警不存在")

        alert.status = "acknowledged"
        alert.acknowledged_by = user.sub
        alert.acknowledged_at = datetime.now()
        db.commit()

        logger.info("管理员 %s 确认资源预警 %s", user.sub, alert_id)
        return {"message": "预警已确认", "alert_id": alert_id}
    finally:
        db.close()


@router.put("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    resolution: str = Query("", description="解决方案"),
    user: TokenPayload = Depends(get_current_user),
):
    """解决资源预警"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import ResourceAlert
    from datetime import datetime

    db = SessionLocal()
    try:
        alert = db.query(ResourceAlert).filter(ResourceAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="预警不存在")

        alert.status = "resolved"
        alert.resolved_at = datetime.now()
        alert.resolution = resolution
        db.commit()

        logger.info("管理员 %s 解决资源预警 %s", user.sub, alert_id)
        return {"message": "预警已解决", "alert_id": alert_id}
    finally:
        db.close()


@router.get("/alerts/stats")
def get_alert_stats(
    user: TokenPayload = Depends(get_current_user),
):
    """获取预警统计"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import ResourceAlert
    from sqlalchemy import func

    db = SessionLocal()
    try:
        # 按状态统计
        status_stats = db.query(
            ResourceAlert.status,
            func.count(ResourceAlert.id).label("count")
        ).group_by(ResourceAlert.status).all()

        # 按严重程度统计
        severity_stats = db.query(
            ResourceAlert.severity,
            func.count(ResourceAlert.id).label("count")
        ).group_by(ResourceAlert.severity).all()

        # 按类型统计
        type_stats = db.query(
            ResourceAlert.alert_type,
            func.count(ResourceAlert.id).label("count")
        ).group_by(ResourceAlert.alert_type).all()

        return {
            "by_status": {s.status: s.count for s in status_stats},
            "by_severity": {s.severity: s.count for s in severity_stats},
            "by_type": {s.alert_type: s.count for s in type_stats},
            "total": sum(s.count for s in status_stats),
        }
    finally:
        db.close()


# ==================== 报告生成 API ====================


class ReportDateRange(BaseModel):
    """报告日期范围请求（日期可选，默认最近7天）"""
    from_date: Optional[str] = None  # ISO 格式: YYYY-MM-DD
    to_date: Optional[str] = None    # ISO 格式: YYYY-MM-DD


def _parse_date_range(body: Optional[ReportDateRange]) -> tuple:
    """解析日期范围，默认最近7天"""
    from datetime import datetime as dt_cls, timedelta
    today = dt_cls.now().date()
    from_date_val = body.from_date if body else None
    to_date_val = body.to_date if body else None
    if from_date_val:
        dt_from = dt_cls.fromisoformat(from_date_val)
    else:
        dt_from = dt_cls.combine(today - timedelta(days=7), dt_cls.min.time())
    if to_date_val:
        dt_to = dt_cls.fromisoformat(to_date_val + "T23:59:59")
    else:
        dt_to = dt_cls.combine(today, dt_cls.max.time())
    return dt_from, dt_to


@router.post("/report/agent")
async def generate_agent_report(
    body: Optional[ReportDateRange] = None,
    user: TokenPayload = Depends(get_current_user),
):
    """生成智能体工具路由与 Token 消耗报告（LLM 分析 + 规则 fallback）"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import AgentAuditLog, ToolCallDetail, GeneratedReport
    from sqlalchemy import func
    from datetime import datetime
    import json

    db = SessionLocal()
    try:
        dt_from, dt_to = _parse_date_range(body or ReportDateRange())

        # 查询审计日志
        logs = db.query(AgentAuditLog).filter(
            AgentAuditLog.created_at >= dt_from,
            AgentAuditLog.created_at <= dt_to,
        ).all()

        if not logs:
            raise HTTPException(status_code=404, detail="指定时间段内无审计日志数据")

        total_logs = len(logs)
        total_input = sum(l.input_tokens or 0 for l in logs)
        total_output = sum(l.output_tokens or 0 for l in logs)
        total_tokens = sum(l.total_tokens or 0 for l in logs)

        # 日均计算
        days = max((dt_to - dt_from).days, 1)
        daily_avg = round(total_tokens / days, 1)

        # 意图分布
        intent_counts = {}
        for l in logs:
            intent = l.intent_classification or "unknown"
            intent_counts[intent] = intent_counts.get(intent, 0) + 1

        # 按角色统计 Token 消耗
        role_token_stats = {}
        for l in logs:
            role = l.agent_role or "unknown"
            if role not in role_token_stats:
                role_token_stats[role] = {"input": 0, "output": 0, "total": 0, "count": 0}
            role_token_stats[role]["input"] += l.input_tokens or 0
            role_token_stats[role]["output"] += l.output_tokens or 0
            role_token_stats[role]["total"] += l.total_tokens or 0
            role_token_stats[role]["count"] += 1

        # 按角色统计意图分布
        role_intent_stats = {}
        for l in logs:
            role = l.agent_role or "unknown"
            intent = l.intent_classification or "unknown"
            if role not in role_intent_stats:
                role_intent_stats[role] = {}
            role_intent_stats[role][intent] = role_intent_stats[role].get(intent, 0) + 1

        # Agent 路由分布
        agent_counts = {}
        for l in logs:
            agent = l.routed_agent or "unknown"
            agent_counts[agent] = agent_counts.get(agent, 0) + 1

        # 工具调用分析
        tool_calls = db.query(ToolCallDetail).filter(
            ToolCallDetail.audit_log_id.in_([l.id for l in logs])
        ).all()

        total_tool_calls = len(tool_calls)
        tool_success = sum(1 for t in tool_calls if t.success)
        tool_fail = total_tool_calls - tool_success
        success_rate = round(tool_success / total_tool_calls * 100, 1) if total_tool_calls else 0

        # Top 工具 (带成功率)
        tool_stats = {}
        for t in tool_calls:
            name = t.tool_name
            if name not in tool_stats:
                tool_stats[name] = {"count": 0, "success": 0, "fail": 0}
            tool_stats[name]["count"] += 1
            if t.success:
                tool_stats[name]["success"] += 1
            else:
                tool_stats[name]["fail"] += 1
        top_tools = []
        for name, stats in sorted(tool_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]:
            sr = round(stats["success"] / stats["count"] * 100, 1) if stats["count"] else 0
            top_tools.append({
                "name": name,
                "count": stats["count"],
                "success_rate": sr,
                "avg_latency_ms": 0,
            })

        tool_success_rates = [
            {"name": name, "success_rate": round(s["success"] / s["count"] * 100, 1)}
            for name, s in sorted(tool_stats.items(), key=lambda x: x[1]["count"], reverse=True)
        ]

        # 反馈统计
        positive = sum(1 for l in logs if l.feedback_rating == "thumbs_up")
        negative = sum(1 for l in logs if l.feedback_rating == "thumbs_down")

        # --- 规则引擎 fallback: 异常检测 ---
        fallback_anomalies = []
        high_error_tools = [
            name for name, _ in top_tools
            if sum(1 for t in tool_calls if t.tool_name == name and not t.success) /
               max(sum(1 for t in tool_calls if t.tool_name == name), 1) > 0.3
        ]
        if high_error_tools:
            fallback_anomalies.append(f"以下工具错误率超过30%: {', '.join(high_error_tools)}")
        if negative > positive and (positive + negative) > 5:
            fallback_anomalies.append("负面反馈数量超过正面反馈，建议检查回复质量")

        # --- 规则引擎 fallback: 建议 ---
        fallback_recommendations = []
        if success_rate < 90:
            fallback_recommendations.append("工具调用成功率偏低，建议排查高频失败工具的入参或依赖")
        if total_tokens / max(total_logs, 1) > 3000:
            fallback_recommendations.append("单次对话平均 Token 消耗较高，建议优化 Prompt 长度或启用上下文裁剪")
        if not fallback_recommendations:
            fallback_recommendations.append("当前运行状态良好，继续保持")

        fallback_summary = f"报告期间共 {total_logs} 次 Agent 调用，消耗 {total_tokens} Token，工具成功率 {success_rate}%"

        # --- LLM 智能分析 ---
        llm_summary = ""
        llm_recommendations = []
        llm_anomalies = []
        llm_used = False

        try:
            from ..core import get_llm_client

            # 构建结构化的数据 prompt
            data_context = json.dumps({
                "period": {"from": str(dt_from.date()), "to": str(dt_to.date())},
                "token": {
                    "total": total_tokens, "input": total_input, "output": total_output,
                    "daily_avg": daily_avg, "avg_per_call": round(total_tokens / total_logs, 1),
                    "cost_estimate": round(total_tokens * 0.000002, 4),
                    "by_role": {r: {"input": v["input"], "output": v["output"], "count": v["count"]}
                                for r, v in role_token_stats.items()},
                },
                "intent": {"distribution": intent_counts, "by_role": role_intent_stats},
                "routing": {"agent_distribution": agent_counts},
                "tool": {
                    "total_calls": total_tool_calls, "success": tool_success,
                    "fail": tool_fail, "success_rate": success_rate,
                    "top_tools": top_tools,
                },
                "feedback": {"positive": positive, "negative": negative},
            }, ensure_ascii=False, indent=2)

            system_prompt = (
                "你是一位专业的 AI Agent 运维分析师，擅长分析 Agent 调用模式、Token 消耗和工具使用效率。"
                "请根据提供的 Agent 运营数据生成分析报告。严格按格式输出，每部分以指定标签开头。"
            )
            user_prompt = f"""请分析以下 AI Agent 运营数据并生成报告：

{data_context}

请严格按以下格式输出（每部分以标签开头）：

【智能摘要】
（1-2句话总结核心指标和整体趋势，包含关键数字）

【异常检测】
（列出发现的问题，每条一行，以 "- " 开头。如无异常则写 "未发现明显异常"）

【优化建议】
（列出3-5条具体建议，每条一行，以 "- " 开头，按优先级排序）

【趋势判断】
（一句话判断：负载在上升/下降/稳定）"""

            client = get_llm_client()
            llm_response = await client.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ])

            # 解析 LLM 响应
            import re
            summary_match = re.search(r"【智能摘要】\s*\n?(.*?)(?=【|$)", llm_response, re.DOTALL)
            anomaly_match = re.search(r"【异常检测】\s*\n?(.*?)(?=【|$)", llm_response, re.DOTALL)
            recommend_match = re.search(r"【优化建议】\s*\n?(.*?)(?=【|$)", llm_response, re.DOTALL)

            if summary_match:
                llm_summary = summary_match.group(1).strip()
            if anomaly_match:
                anomaly_text = anomaly_match.group(1).strip()
                llm_anomalies = [line.lstrip("- ").strip() for line in anomaly_text.split("\n")
                                 if line.strip().startswith("-") and len(line.strip()) > 3]
            if recommend_match:
                rec_text = recommend_match.group(1).strip()
                llm_recommendations = [line.lstrip("- ").strip() for line in rec_text.split("\n")
                                       if line.strip().startswith("-") and len(line.strip()) > 3]

            llm_used = bool(llm_summary)
            logger.info("Agent 报告 LLM 分析完成, response_len=%s", len(llm_response))

        except Exception as e:
            logger.warning("Agent 报告 LLM 分析失败，降级规则引擎: %s", e)

        # --- 合并结果 (LLM 优先，规则 fallback) ---
        executive_summary = llm_summary if llm_summary else fallback_summary
        recommendations = llm_recommendations if llm_recommendations else fallback_recommendations
        anomalies = llm_anomalies if llm_anomalies else fallback_anomalies

        # 趋势数据
        trend = "stable"
        if "上升" in llm_summary:
            trend = "rising"
        elif "下降" in llm_summary:
            trend = "declining"

        report_data = {
            "period": {"from": dt_from.date().isoformat(), "to": dt_to.date().isoformat()},
            "executive_summary": executive_summary,
            "llm_analyzed": llm_used,
            "token_analysis": {
                "total": total_tokens,
                "input": total_input,
                "output": total_output,
                "daily_average": daily_avg,
                "trend": trend,
                "cost_estimate": round(total_tokens * 0.000002, 4),
                "by_role": role_token_stats,
            },
            "intent_analysis": {
                "distribution": intent_counts,
                "by_role": role_intent_stats,
                "chart": [{"intent": k, "count": v} for k, v in sorted(intent_counts.items(), key=lambda x: x[1], reverse=True)],
            },
            "routing_analysis": {
                "intent_distribution": intent_counts,
                "agent_distribution": agent_counts,
            },
            "tool_analysis": {
                "total_calls": total_tool_calls,
                "success_count": tool_success,
                "fail_count": tool_fail,
                "success_rate": success_rate,
                "top_tools": top_tools,
                "success_rates": tool_success_rates,
            },
            "feedback_summary": {
                "positive": positive,
                "negative": negative,
                "total": positive + negative,
            },
            "recommendations": recommendations,
            "anomalies": anomalies,
        }

        # 持久化报告
        report = GeneratedReport(
            report_type="agent",
            title=f"智能体报告 ({dt_from.date()} ~ {dt_to.date()})",
            period_from=dt_from,
            period_to=dt_to,
            report_data=report_data,
            generated_by=user.sub,
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        logger.info("管理员 %s 生成智能体报告 #%s", user.sub, report.id)
        return {"report_id": report.id, "report": report_data}
    finally:
        db.close()


@router.post("/report/device")
async def generate_device_report(
    body: Optional[ReportDateRange] = None,
    user: TokenPayload = Depends(get_current_user),
):
    """生成设备使用情况报告（LLM 分析 + 规则 fallback）"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import ResourceMetric, ResourceAlert, GeneratedReport
    from sqlalchemy import func
    from datetime import datetime
    import json

    db = SessionLocal()
    try:
        dt_from, dt_to = _parse_date_range(body or ReportDateRange())

        # 查询资源指标
        metrics = db.query(ResourceMetric).filter(
            ResourceMetric.created_at >= dt_from,
            ResourceMetric.created_at <= dt_to,
        ).all()

        if not metrics:
            raise HTTPException(status_code=404, detail="指定时间段内无资源指标数据")

        # 查询预警
        alerts = db.query(ResourceAlert).filter(
            ResourceAlert.created_at >= dt_from,
            ResourceAlert.created_at <= dt_to,
        ).all()

        # 资源概览
        vram_vals = [m.vram_percent for m in metrics if m.vram_percent is not None]
        gpu_vals = [m.gpu_percent for m in metrics if m.gpu_percent is not None]
        cpu_vals = [m.cpu_percent for m in metrics if m.cpu_percent is not None]
        power_vals = [m.gpu_power_w for m in metrics if m.gpu_power_w is not None]
        temp_vals = [m.gpu_temp_c for m in metrics if m.gpu_temp_c is not None]

        def _avg(lst):
            return round(sum(lst) / len(lst), 1) if lst else None

        def _max_val(lst):
            return round(max(lst), 1) if lst else None

        def _min_val(lst):
            return round(min(lst), 1) if lst else None

        # 负载分布
        load_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for m in metrics:
            level = m.load_level or "low"
            if level in load_counts:
                load_counts[level] += 1

        # 整体状态判定
        avg_vram = _avg(vram_vals)
        avg_gpu = _avg(gpu_vals)
        overall = "normal"
        if avg_vram and avg_vram > 90 or avg_gpu and avg_gpu > 90:
            overall = "critical"
        elif avg_vram and avg_vram > 75 or avg_gpu and avg_gpu > 75:
            overall = "warning"

        # 预警统计
        critical_alerts = sum(1 for a in alerts if a.severity == "critical")
        warning_alerts = sum(1 for a in alerts if a.severity == "warning")
        alert_type_counts = {}
        for a in alerts:
            t = a.alert_type or "unknown"
            alert_type_counts[t] = alert_type_counts.get(t, 0) + 1
        top_alerts = sorted(alert_type_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # 健康评分（0-100）
        health_score = 100.0
        if avg_vram:
            health_score -= max(0, (avg_vram - 50) * 0.5)
        if avg_gpu:
            health_score -= max(0, (avg_gpu - 50) * 0.3)
        if _avg(temp_vals) and _avg(temp_vals) > 70:
            health_score -= (_avg(temp_vals) - 70) * 0.5
        health_score -= critical_alerts * 5
        health_score -= warning_alerts * 1
        health_score = max(0, min(100, round(health_score, 1)))

        # --- 规则引擎 fallback: 建议 ---
        fallback_recommendations = []
        if avg_vram and avg_vram > 80:
            fallback_recommendations.append("VRAM 使用率长期偏高，建议优化模型加载策略或增加显存")
        if _avg(temp_vals) and _avg(temp_vals) > 75:
            fallback_recommendations.append("GPU 温度偏高，建议检查散热或降低负载")
        if critical_alerts > 10:
            fallback_recommendations.append(f"报告期间出现 {critical_alerts} 次严重预警，建议排查根因")
        if load_counts["critical"] > len(metrics) * 0.1:
            fallback_recommendations.append("超过10%的时间处于 critical 负载，建议启用自动降级策略")
        if not fallback_recommendations:
            fallback_recommendations.append("设备运行状态良好，继续保持当前配置")

        # --- LLM 智能分析 ---
        llm_summary = ""
        llm_recommendations = []
        llm_health_assessment = ""
        llm_used = False

        try:
            from ..core import get_llm_client

            resource_data = {
                "period": {"from": str(dt_from.date()), "to": str(dt_to.date()), "samples": len(metrics)},
                "vram": {"avg": avg_vram, "max": _max_val(vram_vals), "min": _min_val(vram_vals)},
                "gpu": {"avg": avg_gpu, "max": _max_val(gpu_vals), "min": _min_val(gpu_vals)},
                "cpu": {"avg": _avg(cpu_vals), "max": _max_val(cpu_vals), "min": _min_val(cpu_vals)},
                "power_temp": {
                    "gpu_power_w": {"avg": _avg(power_vals), "max": _max_val(power_vals)},
                    "gpu_temp_c": {"avg": _avg(temp_vals), "max": _max_val(temp_vals)},
                },
                "load_distribution": load_counts,
                "overall_status": overall,
                "alerts": {
                    "total": len(alerts), "critical": critical_alerts, "warning": warning_alerts,
                    "top_types": [{"type": t, "count": c} for t, c in top_alerts],
                },
                "health_score": health_score,
            }

            system_prompt = (
                "你是一位专业的硬件资源运维分析师，擅长分析 GPU/NPU 服务器资源使用情况和预警趋势。"
                "请根据提供的设备资源数据生成运维分析报告。严格按格式输出，每部分以指定标签开头。"
            )
            user_prompt = f"""请分析以下设备资源数据并生成报告：

{json.dumps(resource_data, ensure_ascii=False, indent=2)}

请严格按以下格式输出（每部分以标签开头）：

【运维摘要】
（1-2句话总结设备整体运行状态和关键指标）

【健康评估】
（对系统健康状态给出判断，说明主要风险点。如健康则写"系统运行正常"）

【优化建议】
（列出3-5条具体建议，每条一行，以 "- " 开头，按优先级排序）"""

            client = get_llm_client()
            llm_response = await client.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ])

            # 解析 LLM 响应
            import re
            summary_match = re.search(r"【运维摘要】\s*\n?(.*?)(?=【|$)", llm_response, re.DOTALL)
            health_match = re.search(r"【健康评估】\s*\n?(.*?)(?=【|$)", llm_response, re.DOTALL)
            recommend_match = re.search(r"【优化建议】\s*\n?(.*?)(?=【|$)", llm_response, re.DOTALL)

            if summary_match:
                llm_summary = summary_match.group(1).strip()
            if health_match:
                llm_health_assessment = health_match.group(1).strip()
            if recommend_match:
                rec_text = recommend_match.group(1).strip()
                llm_recommendations = [line.lstrip("- ").strip() for line in rec_text.split("\n")
                                       if line.strip().startswith("-") and len(line.strip()) > 3]

            llm_used = bool(llm_summary)
            logger.info("Device 报告 LLM 分析完成, response_len=%s", len(llm_response))

        except Exception as e:
            logger.warning("Device 报告 LLM 分析失败，降级规则引擎: %s", e)

        # --- 合并结果 (LLM 优先，规则 fallback) ---
        executive_summary = llm_summary
        recommendations = llm_recommendations if llm_recommendations else fallback_recommendations

        report_data = {
            "period": {"from": dt_from.date().isoformat(), "to": dt_to.date().isoformat()},
            "executive_summary": executive_summary,
            "health_assessment": llm_health_assessment,
            "llm_analyzed": llm_used,
            "device_overview": {
                "gpu": "AMD Radeon (详见系统状态接口)",
                "vram_total": "详见系统状态接口",
                "npu": "AMD NPU (详见系统状态接口)",
            },
            "resource_summary": {
                "vram": {"avg": avg_vram, "max": _max_val(vram_vals), "min": _min_val(vram_vals)},
                "gpu": {"avg": avg_gpu, "max": _max_val(gpu_vals), "min": _min_val(gpu_vals)},
                "cpu": {"avg": _avg(cpu_vals), "max": _max_val(cpu_vals), "min": _min_val(cpu_vals)},
                "overall_status": overall,
            },
            "power_thermal": {
                "gpu_power": {"avg": _avg(power_vals), "max": _max_val(power_vals)},
                "gpu_temp": {"avg": _avg(temp_vals), "max": _max_val(temp_vals)},
            },
            "load_distribution": load_counts,
            "alert_summary": {
                "total": len(alerts),
                "critical": critical_alerts,
                "warning": warning_alerts,
                "top_alerts": [{"type": t, "count": c} for t, c in top_alerts],
            },
            "recommendations": recommendations,
            "health_score": health_score,
        }

        # 持久化报告
        report = GeneratedReport(
            report_type="device",
            title=f"设备报告 ({dt_from.date()} ~ {dt_to.date()})",
            period_from=dt_from,
            period_to=dt_to,
            report_data=report_data,
            generated_by=user.sub,
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        logger.info("管理员 %s 生成设备报告 #%s", user.sub, report.id)
        return {"report_id": report.id, "report": report_data}
    finally:
        db.close()


@router.get("/report/history")
def get_report_history(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    report_type: Optional[str] = Query(None, description="报告类型: agent/device"),
    user: TokenPayload = Depends(get_current_user),
):
    """获取历史报告列表"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import GeneratedReport

    db = SessionLocal()
    try:
        query = db.query(GeneratedReport)
        if report_type:
            query = query.filter(GeneratedReport.report_type == report_type)

        total = query.count()
        reports = (
            query.order_by(GeneratedReport.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "reports": [
                {
                    "id": r.id,
                    "report_type": r.report_type,
                    "title": r.title,
                    "period_from": r.period_from.isoformat() if r.period_from else None,
                    "period_to": r.period_to.isoformat() if r.period_to else None,
                    "generated_by": r.generated_by,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in reports
            ],
        }
    finally:
        db.close()


@router.get("/report/{report_id}")
def get_report_detail(
    report_id: int,
    user: TokenPayload = Depends(get_current_user),
):
    """获取单个报告详情"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import GeneratedReport

    db = SessionLocal()
    try:
        report = db.query(GeneratedReport).filter(GeneratedReport.id == report_id).first()
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")

        return {
            "id": report.id,
            "report_type": report.report_type,
            "title": report.title,
            "period_from": report.period_from.isoformat() if report.period_from else None,
            "period_to": report.period_to.isoformat() if report.period_to else None,
            "report_data": report.report_data,
            "generated_by": report.generated_by,
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }
    finally:
        db.close()
