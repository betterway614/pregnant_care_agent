"""
资源分析器 - 使用 LLM 分析资源使用模式，生成优化建议

P3 功能：离线分析，非实时决策。
- 定期分析使用模式
- 生成配置优化建议
- 异常原因诊断
- 生成运维报告
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from .resource_monitor import resource_monitor, ResourceState, LoadLevel
from .resource_rules import resource_rule_engine

logger = logging.getLogger(__name__)


@dataclass
class ResourceAnalysis:
    """资源分析结果"""
    timestamp: str
    analysis_type: str  # "pattern" | "anomaly" | "optimization" | "report"
    summary: str
    details: Dict
    recommendations: List[str]
    confidence: float  # 0-1

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "analysis_type": self.analysis_type,
            "summary": self.summary,
            "details": self.details,
            "recommendations": self.recommendations,
            "confidence": self.confidence,
        }


class ResourceAnalyzer:
    """资源分析器 - 使用 LLM 分析资源使用模式"""

    def __init__(self):
        self._last_analysis: Optional[ResourceAnalysis] = None
        self._analysis_history: List[ResourceAnalysis] = []

    async def analyze_usage_pattern(self, hours: int = 24) -> ResourceAnalysis:
        """分析过去 N 小时的使用模式"""
        history = resource_monitor.get_history(limit=1000)

        if not history:
            return ResourceAnalysis(
                timestamp=datetime.now().isoformat(),
                analysis_type="pattern",
                summary="暂无历史数据，无法分析使用模式",
                details={},
                recommendations=["请先启动资源监控以收集数据"],
                confidence=0.0,
            )

        # 计算统计指标
        vram_values = [s.vram_percent for s in history]
        gpu_values = [s.gpu_percent for s in history]
        cpu_values = [s.cpu_percent for s in history]

        stats = {
            "vram": {
                "avg": sum(vram_values) / len(vram_values),
                "max": max(vram_values),
                "min": min(vram_values),
                "samples": len(vram_values),
            },
            "gpu": {
                "avg": sum(gpu_values) / len(gpu_values),
                "max": max(gpu_values),
                "min": min(gpu_values),
            },
            "cpu": {
                "avg": sum(cpu_values) / len(cpu_values),
                "max": max(cpu_values),
                "min": min(cpu_values),
            },
        }

        # 生成分析报告
        recommendations = []
        summary_parts = []

        # VRAM 分析
        if stats["vram"]["avg"] > 0.85:
            summary_parts.append("VRAM 使用率持续偏高")
            recommendations.append("建议切换到保守策略 (conservative)")
            recommendations.append("考虑减少 LLM 上下文长度或并发数")
        elif stats["vram"]["avg"] < 0.40:
            summary_parts.append("VRAM 使用率较低，有优化空间")
            recommendations.append("可以增加批处理大小以提升性能")
            recommendations.append("考虑切换到性能优先策略 (performance)")

        # GPU 分析
        if stats["gpu"]["avg"] > 90:
            summary_parts.append("GPU 使用率接近满载")
            recommendations.append("考虑将部分服务卸载到 CPU 或 NPU")

        # 生成摘要
        if not summary_parts:
            summary_parts.append("资源使用处于正常范围")

        analysis = ResourceAnalysis(
            timestamp=datetime.now().isoformat(),
            analysis_type="pattern",
            summary="；".join(summary_parts),
            details=stats,
            recommendations=recommendations,
            confidence=0.8,
        )

        self._last_analysis = analysis
        self._analysis_history.append(analysis)

        return analysis

    async def diagnose_anomaly(self, state: ResourceState) -> ResourceAnalysis:
        """诊断异常情况"""
        issues = []
        recommendations = []

        # 检查 VRAM 异常
        if state.vram_percent > 0.95:
            issues.append(f"VRAM 使用率极高 ({state.vram_percent:.1%})")
            recommendations.append("立即切换到保守策略")
            recommendations.append("考虑重启服务释放资源")

        # 检查 GPU 异常
        if state.gpu_percent > 95:
            issues.append(f"GPU 使用率极高 ({state.gpu_percent:.1f}%)")
            recommendations.append("检查是否有异常进程占用 GPU")

        # 检查 CPU 异常
        if state.cpu_percent > 90:
            issues.append(f"CPU 使用率极高 ({state.cpu_percent:.1f}%)")
            recommendations.append("检查是否有 CPU 密集型任务")

        # 检查 NPU 状态
        if not state.npu_available:
            issues.append("NPU 设备不可用")
            recommendations.append("检查 NPU 驱动和 XRT 安装")

        if not issues:
            summary = "未发现异常"
            confidence = 0.9
        else:
            summary = f"发现 {len(issues)} 个异常: " + "；".join(issues)
            confidence = 0.7

        analysis = ResourceAnalysis(
            timestamp=datetime.now().isoformat(),
            analysis_type="anomaly",
            summary=summary,
            details={
                "issues": issues,
                "vram_percent": state.vram_percent,
                "gpu_percent": state.gpu_percent,
                "cpu_percent": state.cpu_percent,
                "npu_available": state.npu_available,
            },
            recommendations=recommendations,
            confidence=confidence,
        )

        self._last_analysis = analysis
        self._analysis_history.append(analysis)

        return analysis

    async def generate_optimization_report(self) -> ResourceAnalysis:
        """生成优化报告"""
        state = resource_monitor.get_current_state()
        adjustments = resource_rule_engine.get_adjustments_summary(state)

        # 分析调整建议
        changes_needed = [a for a in adjustments if a["needs_update"]]

        recommendations = []
        for adj in changes_needed:
            service = adj["service"]
            for change in adj["changes"]:
                recommendations.append(f"{service}: {change}")

        if not recommendations:
            summary = "当前配置已是最优，无需调整"
        else:
            summary = f"发现 {len(recommendations)} 项优化建议"

        analysis = ResourceAnalysis(
            timestamp=datetime.now().isoformat(),
            analysis_type="optimization",
            summary=summary,
            details={
                "current_state": state.to_dict(),
                "adjustments": adjustments,
                "changes_count": len(changes_needed),
            },
            recommendations=recommendations,
            confidence=0.85,
        )

        self._last_analysis = analysis
        self._analysis_history.append(analysis)

        return analysis

    async def generate_daily_report(self) -> ResourceAnalysis:
        """生成每日运维报告"""
        history = resource_monitor.get_history(limit=1000)

        if not history:
            return ResourceAnalysis(
                timestamp=datetime.now().isoformat(),
                analysis_type="report",
                summary="暂无数据生成报告",
                details={},
                recommendations=[],
                confidence=0.0,
            )

        # 计算每日统计
        vram_values = [s.vram_percent for s in history]
        gpu_values = [s.gpu_percent for s in history]
        cpu_values = [s.cpu_percent for s in history]

        # 统计负载级别分布
        load_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for s in history:
            level = resource_monitor.get_load_level(s)
            load_counts[level.value] += 1

        total_samples = len(history)

        report_details = {
            "period": {
                "start": history[0].timestamp,
                "end": history[-1].timestamp,
                "samples": total_samples,
            },
            "vram": {
                "avg": sum(vram_values) / len(vram_values),
                "max": max(vram_values),
                "p95": sorted(vram_values)[int(len(vram_values) * 0.95)],
            },
            "gpu": {
                "avg": sum(gpu_values) / len(gpu_values),
                "max": max(gpu_values),
            },
            "cpu": {
                "avg": sum(cpu_values) / len(cpu_values),
                "max": max(cpu_values),
            },
            "load_distribution": {
                level: f"{count / total_samples:.1%}"
                for level, count in load_counts.items()
            },
        }

        # 生成建议
        recommendations = []
        if load_counts["critical"] > 0:
            recommendations.append("存在 CRITICAL 负载，建议优化资源配置")
        if load_counts["high"] > total_samples * 0.3:
            recommendations.append("高负载时间较长，建议增加资源或优化策略")

        summary = f"过去 {total_samples} 个采样点，平均 VRAM: {report_details['vram']['avg']:.1%}"

        analysis = ResourceAnalysis(
            timestamp=datetime.now().isoformat(),
            analysis_type="report",
            summary=summary,
            details=report_details,
            recommendations=recommendations,
            confidence=0.9,
        )

        self._last_analysis = analysis
        self._analysis_history.append(analysis)

        return analysis

    def get_last_analysis(self) -> Optional[ResourceAnalysis]:
        """获取最后一次分析结果"""
        return self._last_analysis

    def get_analysis_history(self, limit: int = 10) -> List[ResourceAnalysis]:
        """获取分析历史"""
        return self._analysis_history[-limit:]


# 全局单例
resource_analyzer = ResourceAnalyzer()
