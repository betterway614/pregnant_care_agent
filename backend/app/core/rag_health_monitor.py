"""RAG 运行时健康监控

通过 APScheduler 后台定时探测 pgvector 连接和嵌入服务可用性，
在 RAG 组件不可用时更新降级标志、记录日志，供运维和 API 查询。

遵循与 followup_scheduler.py 相同的 BackgroundScheduler + 模块单例模式。

查询接口:
    - get_health_status() -> dict: 获取最新健康检查结果
    - agno_knowledge.is_rag_degraded() / get_rag_degraded_reason(): 降级标志
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# 模块级单例
_scheduler: Optional[BackgroundScheduler] = None

# 最新健康状态 (线程安全: 仅由 scheduler job 写入，外部只读)
_latest_health: dict = {
    "embedding_service": "unknown",   # "healthy" | "unreachable" | "error"
    "pgvector": "unknown",            # "healthy" | "unreachable" | "error"
    "last_check_time": None,          # ISO 时间戳
    "consecutive_failures": 0,        # 连续失败次数
    "degraded": False,                # 当前是否降级
    "degraded_reason": "",            # 降级原因
}


def get_health_status() -> dict:
    """获取最新 RAG 健康检查结果 (线程安全只读)"""
    return dict(_latest_health)  # 返回浅拷贝


def _check_embedding_service(timeout: float = 3.0) -> dict:
    """探测嵌入服务 (BGE-M3 on port 8081) 健康状态

    Returns:
        {"status": "healthy"|"unreachable", "detail": str, "latency_ms": float}
    """
    import requests
    from ..config import settings

    # 从 embedding_api_url 提取实际的 health 端点
    # embedding_api_url 格式: "http://localhost:8081/v1" 或 "https://dashscope.aliyuncs.com/compatible-mode/v1"
    base_url = settings.embedding_api_url.rstrip("/")
    if base_url.endswith("/v1"):
        health_url = base_url.rsplit("/v1", 1)[0] + "/health"
    else:
        health_url = base_url + "/health"

    start = datetime.now(timezone.utc)
    try:
        resp = requests.get(health_url, timeout=timeout)
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        if resp.status_code == 200:
            data = resp.json()
            if data.get("model_loaded"):
                return {
                    "status": "healthy",
                    "detail": f"model={data.get('model_name', 'unknown')}, device={data.get('device', 'unknown')}",
                    "latency_ms": round(latency_ms, 1),
                }
            return {
                "status": "unreachable",
                "detail": "model not loaded",
                "latency_ms": round(latency_ms, 1),
            }
        return {
            "status": "unreachable",
            "detail": f"HTTP {resp.status_code}",
            "latency_ms": round(latency_ms, 1),
        }
    except requests.Timeout:
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return {"status": "unreachable", "detail": "timeout", "latency_ms": round(latency_ms, 1)}
    except requests.ConnectionError:
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return {"status": "unreachable", "detail": "connection refused", "latency_ms": round(latency_ms, 1)}
    except Exception as e:
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return {"status": "error", "detail": str(e)[:200], "latency_ms": round(latency_ms, 1)}


def _check_pgvector(timeout: float = 5.0) -> dict:
    """探测 pgvector 连接和检索可用性

    通过尝试 knowledge.search() 验证完整的向量检索链路:
    pgvector 连接 + 表存在 + 向量检索能力。

    Returns:
        {"status": "healthy"|"unreachable"|"empty", "detail": str, "latency_ms": float}
    """
    import time

    start = time.monotonic()
    try:
        from .agno_knowledge import knowledge

        if knowledge is None:
            latency_ms = (time.monotonic() - start) * 1000
            return {"status": "unreachable", "detail": "knowledge instance is None — check DB_TYPE=postgres and RAG_ENABLED", "latency_ms": round(latency_ms, 1)}

        results = knowledge.search(query="health_check", max_results=1)
        latency_ms = (time.monotonic() - start) * 1000

        if results:
            return {
                "status": "healthy",
                "detail": f"{len(results)} chunks returned",
                "latency_ms": round(latency_ms, 1),
            }
        return {
            "status": "empty",
            "detail": "search returned 0 results (table may not have ingested documents)",
            "latency_ms": round(latency_ms, 1),
        }
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        return {"status": "unreachable", "detail": str(e)[:200], "latency_ms": round(latency_ms, 1)}


def _health_check_job():
    """定时健康检查任务 — 由 APScheduler 调用"""
    global _latest_health

    # 嵌入服务检查
    embedding = _check_embedding_service()

    # pgvector 检查
    pgvector = _check_pgvector()

    # 判定降级状态
    embedding_ok = embedding["status"] == "healthy"
    pgvector_ok = pgvector["status"] in ("healthy", "empty")  # empty 也算可用 (表存在只是无数据)

    was_degraded = _latest_health.get("degraded", False)
    is_degraded = not (embedding_ok and pgvector_ok)

    if is_degraded:
        _latest_health["consecutive_failures"] += 1
        reasons = []
        if not embedding_ok:
            reasons.append(f"embedding_service: {embedding['status']} ({embedding['detail']})")
        if not pgvector_ok:
            reasons.append(f"pgvector: {pgvector['status']} ({pgvector['detail']})")
        reason_str = "; ".join(reasons)

        if not was_degraded:
            logger.warning("[RAG Health] 进入降级状态: %s", reason_str)
        elif _latest_health["consecutive_failures"] % 12 == 0:
            # 每 1 小时 (12次 × 5分钟) 重复警告一次，避免日志泛滥
            logger.warning(
                "[RAG Health] 持续降级 (连续%d次检查失败): %s",
                _latest_health["consecutive_failures"], reason_str,
            )
    else:
        _latest_health["consecutive_failures"] = 0
        if was_degraded:
            logger.info("[RAG Health] 恢复正常: embedding=%s pgvector=%s", embedding["status"], pgvector["status"])

    _latest_health.update({
        "embedding_service": embedding["status"],
        "pgvector": pgvector["status"],
        "last_check_time": datetime.now(timezone.utc).isoformat(),
        "degraded": is_degraded,
        "degraded_reason": (
            ""
            if not is_degraded
            else "; ".join(
                f"{s}: {d}" for s, d in [
                    ("embedding", embedding["detail"]) if not embedding_ok else None,
                    ("pgvector", pgvector["detail"]) if not pgvector_ok else None,
                ] if s is not None
            )
        ),
        "_detail": {
            "embedding": embedding,
            "pgvector": pgvector,
        },
    })

    # 同步更新 agno_knowledge 模块的降级标志
    try:
        import app.core.agno_knowledge as kb_module
        kb_module._rag_degraded = is_degraded
        kb_module._rag_degraded_reason = _latest_health["degraded_reason"]
    except Exception:
        pass


def start_monitor(interval_minutes: int = 5) -> Optional[BackgroundScheduler]:
    """启动 RAG 健康监控调度器。幂等：重复调用不会创建第二个调度器。

    Args:
        interval_minutes: 检查间隔 (分钟)，默认 5 分钟

    Returns:
        BackgroundScheduler 实例，或 None (当 RAG 未启用时)
    """
    global _scheduler
    if _scheduler is not None:
        logger.info("RAG 健康监控已在运行，跳过重复启动")
        return _scheduler

    from ..config import settings

    if not settings.rag_enabled:
        logger.info("RAG 健康监控跳过：RAG 未启用 (rag_enabled=false)")
        return None

    _scheduler = BackgroundScheduler(daemon=True)

    trigger = IntervalTrigger(minutes=interval_minutes)
    _scheduler.add_job(
        _health_check_job,
        trigger=trigger,
        id="rag_health_check",
        name="RAG 健康检查",
        misfire_grace_time=max(60, interval_minutes * 15),  # 错过最多 15% 周期仍补执行
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "RAG 健康监控已启动: 间隔 %d 分钟, 检查 embedding(%s) + pgvector",
        interval_minutes,
        settings.embedding_api_url,
    )

    # 启动后立即执行一次检查
    try:
        _health_check_job()
    except Exception as e:
        logger.warning("RAG 初始健康检查失败: %s", e)

    return _scheduler


def stop_monitor():
    """停止 RAG 健康监控调度器"""
    global _scheduler, _latest_health
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        _latest_health["degraded"] = False
        _latest_health["degraded_reason"] = ""
        logger.info("RAG 健康监控已停止")
