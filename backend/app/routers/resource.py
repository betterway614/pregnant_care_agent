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

    logger.info("管理员 {} 更新服务 {} 配置: {}", user.sub, service_name, kwargs)
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

    logger.info("管理员 {} 切换策略为 {}", user.sub, body.policy)
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

    logger.info("管理员 {} 启动资源监控 (间隔: {}s)", user.sub, interval)
    return {"message": f"资源监控已启动 (间隔: {interval}s)"}


@router.post("/monitoring/stop")
def stop_monitoring(user: TokenPayload = Depends(get_current_user)):
    """停止资源监控"""
    _require_admin(user)

    from ..services.resource_service import resource_service
    resource_service.stop_monitoring()

    logger.info("管理员 {} 停止资源监控", user.sub)
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

        logger.info("管理员 {} 确认资源预警 {}", user.sub, alert_id)
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

        logger.info("管理员 {} 解决资源预警 {}", user.sub, alert_id)
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
    """报告日期范围请求"""
    from_date: str  # ISO 格式: YYYY-MM-DD
    to_date: str  # ISO 格式: YYYY-MM-DD


@router.post("/report/agent")
def generate_agent_report(
    body: ReportDateRange,
    user: TokenPayload = Depends(get_current_user),
):
    """生成智能体工具路由与 Token 消耗报告"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import AgentAuditLog, ToolCallDetail, GeneratedReport
    from sqlalchemy import func
    from datetime import datetime

    db = SessionLocal()
    try:
        dt_from = datetime.fromisoformat(body.from_date)
        dt_to = datetime.fromisoformat(body.to_date + "T23:59:59")

        # 查询审计日志
        logs = db.query(AgentAuditLog).filter(
            AgentAuditLog.created_at >= dt_from,
            AgentAuditLog.created_at <= dt_to,
        ).all()

        if not logs:
            return {"message": "指定时间段内无审计日志数据", "report": None}

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

        # Top 工具
        tool_name_counts = {}
        for t in tool_calls:
            name = t.tool_name
            tool_name_counts[name] = tool_name_counts.get(name, 0) + 1
        top_tools = sorted(tool_name_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # 反馈统计
        positive = sum(1 for l in logs if l.feedback_rating == "thumbs_up")
        negative = sum(1 for l in logs if l.feedback_rating == "thumbs_down")

        # 异常检测
        anomalies = []
        high_error_tools = [
            name for name, _ in top_tools
            if sum(1 for t in tool_calls if t.tool_name == name and not t.success) /
               max(sum(1 for t in tool_calls if t.tool_name == name), 1) > 0.3
        ]
        if high_error_tools:
            anomalies.append(f"以下工具错误率超过30%: {', '.join(high_error_tools)}")
        if negative > positive and (positive + negative) > 5:
            anomalies.append("负面反馈数量超过正面反馈，建议检查回复质量")

        # 建议
        recommendations = []
        if success_rate < 90:
            recommendations.append("工具调用成功率偏低，建议排查高频失败工具的入参或依赖")
        if total_tokens / max(total_logs, 1) > 3000:
            recommendations.append("单次对话平均 Token 消耗较高，建议优化 Prompt 长度或启用上下文裁剪")
        if not recommendations:
            recommendations.append("当前运行状态良好，继续保持")

        report_data = {
            "period": {"from": body.from_date, "to": body.to_date},
            "executive_summary": f"报告期间共 {total_logs} 次 Agent 调用，消耗 {total_tokens} Token，工具成功率 {success_rate}%",
            "token_analysis": {
                "total": total_tokens,
                "input": total_input,
                "output": total_output,
                "daily_average": daily_avg,
                "trend": "stable",
                "cost_estimate": round(total_tokens * 0.000002, 4),
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
                "top_tools": [{"name": n, "count": c} for n, c in top_tools],
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
            title=f"智能体报告 ({body.from_date} ~ {body.to_date})",
            period_from=dt_from,
            period_to=dt_to,
            report_data=report_data,
            generated_by=user.sub,
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        logger.info("管理员 {} 生成智能体报告 #{}", user.sub, report.id)
        return {"report_id": report.id, "report": report_data}
    finally:
        db.close()


@router.post("/report/device")
def generate_device_report(
    body: ReportDateRange,
    user: TokenPayload = Depends(get_current_user),
):
    """生成设备使用情况报告"""
    _require_admin(user)

    from ..database import SessionLocal
    from ..models.models import ResourceMetric, ResourceAlert, GeneratedReport
    from sqlalchemy import func
    from datetime import datetime

    db = SessionLocal()
    try:
        dt_from = datetime.fromisoformat(body.from_date)
        dt_to = datetime.fromisoformat(body.to_date + "T23:59:59")

        # 查询资源指标
        metrics = db.query(ResourceMetric).filter(
            ResourceMetric.created_at >= dt_from,
            ResourceMetric.created_at <= dt_to,
        ).all()

        if not metrics:
            return {"message": "指定时间段内无资源指标数据", "report": None}

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

        # 建议
        recommendations = []
        if avg_vram and avg_vram > 80:
            recommendations.append("VRAM 使用率长期偏高，建议优化模型加载策略或增加显存")
        if _avg(temp_vals) and _avg(temp_vals) > 75:
            recommendations.append("GPU 温度偏高，建议检查散热或降低负载")
        if critical_alerts > 10:
            recommendations.append(f"报告期间出现 {critical_alerts} 次严重预警，建议排查根因")
        if load_counts["critical"] > len(metrics) * 0.1:
            recommendations.append("超过10%的时间处于 critical 负载，建议启用自动降级策略")
        if not recommendations:
            recommendations.append("设备运行状态良好，继续保持当前配置")

        report_data = {
            "period": {"from": body.from_date, "to": body.to_date},
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
            title=f"设备报告 ({body.from_date} ~ {body.to_date})",
            period_from=dt_from,
            period_to=dt_to,
            report_data=report_data,
            generated_by=user.sub,
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        logger.info("管理员 {} 生成设备报告 #{}", user.sub, report.id)
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
