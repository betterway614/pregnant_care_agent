"""
资源分析器 - 使用 LLM 分析资源使用模式，生成优化建议

P3 功能：离线分析，非实时决策。
- 定期分析使用模式
- 生成配置优化建议
- 异常原因诊断
- 生成运维报告

架构：LLM 优先 + 规则引擎 fallback
- LLM 可用时：调用 get_llm_client().chat() 进行智能分析
- LLM 不可用时：降级到规则引擎（阈值判断 + 统计计算）
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
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
    """资源分析器 - 使用 LLM 分析资源使用模式（规则引擎 fallback）"""

    def __init__(self):
        self._last_analysis: Optional[ResourceAnalysis] = None
        self._analysis_history: List[ResourceAnalysis] = []

    # ------------------------------------------------------------------
    # LLM 调用辅助方法
    # ------------------------------------------------------------------

    async def _call_llm_for_analysis(
        self, system_prompt: str, user_prompt: str
    ) -> Optional[str]:
        """调用 LLM 进行分析，失败返回 None

        Args:
            system_prompt: 系统角色提示
            user_prompt: 用户数据提示

        Returns:
            LLM 响应文本，失败时返回 None
        """
        try:
            from ..core import get_llm_client
            client = get_llm_client()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            result = await client.chat(messages)
            return result
        except Exception as e:
            logger.warning("LLM 分析调用失败，降级规则引擎: %s", e)
            return None

    # ------------------------------------------------------------------
    # 使用模式分析
    # ------------------------------------------------------------------

    async def analyze_usage_pattern(self, hours: int = 24) -> ResourceAnalysis:
        """分析过去 N 小时的使用模式（LLM 优先，规则 fallback）"""
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

        # 计算统计指标（规则引擎用）
        vram_values = [s.vram_percent for s in history]
        gpu_values = [s.gpu_percent for s in history]
        cpu_values = [s.cpu_percent for s in history]

        stats = {
            "vram": {
                "avg": round(sum(vram_values) / len(vram_values), 1),
                "max": round(max(vram_values), 1),
                "min": round(min(vram_values), 1),
                "samples": len(vram_values),
            },
            "gpu": {
                "avg": round(sum(gpu_values) / len(gpu_values), 1),
                "max": round(max(gpu_values), 1),
                "min": round(min(gpu_values), 1),
            },
            "cpu": {
                "avg": round(sum(cpu_values) / len(cpu_values), 1),
                "max": round(max(cpu_values), 1),
                "min": round(min(cpu_values), 1),
            },
        }

        # 尝试 LLM 分析
        system_prompt = (
            "你是一位专业的硬件资源运维分析师，擅长分析 GPU/NPU 资源使用模式。"
            "请根据提供的统计数据生成简洁、专业的分析报告。"
            "只输出纯文本，不要使用 Markdown 代码块。"
        )
        user_prompt = f"""请分析过去 {hours} 小时的资源使用模式：

【VRAM 显存】
- 平均: {stats['vram']['avg']}%
- 最高: {stats['vram']['max']}%
- 最低: {stats['vram']['min']}%
- 采样点: {stats['vram']['samples']}

【GPU 使用率】
- 平均: {stats['gpu']['avg']}%
- 最高: {stats['gpu']['max']}%
- 最低: {stats['gpu']['min']}%

【CPU 使用率】
- 平均: {stats['cpu']['avg']}%
- 最高: {stats['cpu']['max']}%
- 最低: {stats['cpu']['min']}%

请输出：
1. 模式总结（1-2句）
2. 趋势判断（负载在上升/下降/稳定）
3. 优化建议（3-5条，编号列表）"""

        llm_result = await self._call_llm_for_analysis(system_prompt, user_prompt)

        if llm_result:
            # 从 LLM 响应中提取各部分
            summary, recommendations = self._parse_llm_analysis(llm_result)
            analysis = ResourceAnalysis(
                timestamp=datetime.now().isoformat(),
                analysis_type="pattern",
                summary=summary,
                details=stats,
                recommendations=recommendations,
                confidence=0.85,
            )
        else:
            # 规则引擎 fallback
            recommendations = []
            summary_parts = []

            if stats["vram"]["avg"] > 0.85:
                summary_parts.append("VRAM 使用率持续偏高")
                recommendations.append("建议切换到保守策略 (conservative)")
                recommendations.append("考虑减少 LLM 上下文长度或并发数")
            elif stats["vram"]["avg"] < 0.40:
                summary_parts.append("VRAM 使用率较低，有优化空间")
                recommendations.append("可以增加批处理大小以提升性能")
                recommendations.append("考虑切换到性能优先策略 (performance)")

            if stats["gpu"]["avg"] > 90:
                summary_parts.append("GPU 使用率接近满载")
                recommendations.append("考虑将部分服务卸载到 CPU 或 NPU")

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

    # ------------------------------------------------------------------
    # 异常诊断
    # ------------------------------------------------------------------

    async def diagnose_anomaly(self, state: ResourceState) -> ResourceAnalysis:
        """诊断异常情况（LLM 优先，规则 fallback）"""
        issues = []
        recommendations = []

        # 规则检测
        if state.vram_percent > 0.95:
            issues.append(f"VRAM 使用率极高 ({state.vram_percent:.1%})")
            recommendations.append("立即切换到保守策略")
            recommendations.append("考虑重启服务释放资源")
        if state.gpu_percent > 95:
            issues.append(f"GPU 使用率极高 ({state.gpu_percent:.1f}%)")
            recommendations.append("检查是否有异常进程占用 GPU")
        if state.cpu_percent > 90:
            issues.append(f"CPU 使用率极高 ({state.cpu_percent:.1f}%)")
            recommendations.append("检查是否有 CPU 密集型任务")
        if not state.npu_available:
            issues.append("NPU 设备不可用")
            recommendations.append("检查 NPU 驱动和 XRT 安装")

        # 尝试 LLM 诊断
        system_prompt = (
            "你是一位专业的硬件故障诊断专家，擅长分析 GPU/NPU 系统的异常情况。"
            "请根据提供的资源状态数据进行根因分析和影响评估。"
            "只输出纯文本，不要使用 Markdown 代码块。"
        )
        user_prompt = f"""请诊断当前资源异常：

【资源状态】
- VRAM 使用率: {state.vram_percent:.1%}
- VRAM 空闲: {state.vram_free_gb:.1f} GB / {state.vram_total_gb:.1f} GB
- GPU 使用率: {state.gpu_percent:.1f}%
- CPU 使用率: {state.cpu_percent:.1f}%
- NPU 可用: {'是' if state.npu_available else '否'}

【规则检测到的异常】
{chr(10).join(f'- {i}' for i in issues) if issues else '未检测到明显异常'}

请输出：
1. 异常根因分析（1-2句，如无异常则说明"当前运行正常"）
2. 影响评估（对服务质量的影响程度）
3. 修复建议（3-5条，按优先级排序）"""

        llm_result = await self._call_llm_for_analysis(system_prompt, user_prompt)

        if llm_result:
            summary, llm_recommendations = self._parse_llm_analysis(llm_result)
            # 合并 LLM 建议和规则建议
            recommendations = llm_recommendations if llm_recommendations else recommendations
        else:
            if not issues:
                summary = "未发现异常"
            else:
                summary = f"发现 {len(issues)} 个异常: " + "；".join(issues)

        if not issues:
            confidence = 0.9
        elif llm_result:
            confidence = 0.85
        else:
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

    # ------------------------------------------------------------------
    # 优化报告
    # ------------------------------------------------------------------

    async def generate_optimization_report(self) -> ResourceAnalysis:
        """生成优化报告（LLM 优先，规则 fallback）"""
        state = resource_monitor.get_current_state()
        adjustments = resource_rule_engine.get_adjustments_summary(state)

        changes_needed = [a for a in adjustments if a["needs_update"]]

        # 规则建议
        rule_recommendations = []
        for adj in changes_needed:
            service = adj["service"]
            for change in adj["changes"]:
                rule_recommendations.append(f"{service}: {change}")

        # 尝试 LLM 优化分析
        system_prompt = (
            "你是一位专业的系统性能优化专家，擅长为 GPU/NPU 异构计算环境提供优化建议。"
            "请根据提供的资源状态和调整方案生成专业建议。"
            "只输出纯文本，不要使用 Markdown 代码块。"
        )
        adjustments_json = json.dumps(adjustments, ensure_ascii=False, indent=2)
        current_state = state.to_dict()
        user_prompt = f"""请根据以下信息生成优化报告：

【当前资源状态】
{json.dumps(current_state, ensure_ascii=False, indent=2)}

【调整方案（规则引擎计算）】
{adjustments_json}

【需要变更的项】
{json.dumps(changes_needed, ensure_ascii=False, indent=2) if changes_needed else '当前配置已是最优'}

请输出：
1. 优化总结（1-2句，当前配置是否需要调整）
2. 优化建议（按优先级排序，3-5条）"""

        llm_result = await self._call_llm_for_analysis(system_prompt, user_prompt)

        if llm_result:
            summary, llm_recommendations = self._parse_llm_analysis(llm_result)
            recommendations = llm_recommendations if llm_recommendations else rule_recommendations
            confidence = 0.85
        else:
            if not rule_recommendations:
                summary = "当前配置已是最优，无需调整"
            else:
                summary = f"发现 {len(rule_recommendations)} 项优化建议"
            recommendations = rule_recommendations
            confidence = 0.8

        analysis = ResourceAnalysis(
            timestamp=datetime.now().isoformat(),
            analysis_type="optimization",
            summary=summary,
            details={
                "current_state": current_state,
                "adjustments": adjustments,
                "changes_count": len(changes_needed),
            },
            recommendations=recommendations,
            confidence=confidence,
        )

        self._last_analysis = analysis
        self._analysis_history.append(analysis)
        return analysis

    # ------------------------------------------------------------------
    # 每日运维报告
    # ------------------------------------------------------------------

    async def generate_daily_report(self) -> ResourceAnalysis:
        """生成每日运维报告（LLM 优先，规则 fallback）"""
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
                "avg": round(sum(vram_values) / len(vram_values), 1),
                "max": round(max(vram_values), 1),
                "p95": round(sorted(vram_values)[int(len(vram_values) * 0.95)], 1),
            },
            "gpu": {
                "avg": round(sum(gpu_values) / len(gpu_values), 1),
                "max": round(max(gpu_values), 1),
            },
            "cpu": {
                "avg": round(sum(cpu_values) / len(cpu_values), 1),
                "max": round(max(cpu_values), 1),
            },
            "load_distribution": {
                level: f"{count / total_samples:.1%}"
                for level, count in load_counts.items()
            },
        }

        # 规则建议
        rule_recommendations = []
        if load_counts["critical"] > 0:
            rule_recommendations.append("存在 CRITICAL 负载，建议优化资源配置")
        if load_counts["high"] > total_samples * 0.3:
            rule_recommendations.append("高负载时间较长，建议增加资源或优化策略")

        # 尝试 LLM 分析
        system_prompt = (
            "你是一位专业的运维报告撰写专家，擅长分析硬件资源使用数据并生成运维总结。"
            "请根据提供的统计数据生成简洁的每日运维报告。"
            "只输出纯文本，不要使用 Markdown 代码块。"
        )
        user_prompt = f"""请根据以下数据生成每日运维报告：

【报告时段】
- 开始: {report_details['period']['start']}
- 结束: {report_details['period']['end']}
- 采样点数: {total_samples}

【VRAM 显存】
- 平均: {report_details['vram']['avg']}%
- 最高: {report_details['vram']['max']}%
- P95: {report_details['vram']['p95']}%

【GPU 使用率】
- 平均: {report_details['gpu']['avg']}%
- 最高: {report_details['gpu']['max']}%

【CPU 使用率】
- 平均: {report_details['cpu']['avg']}%
- 最高: {report_details['cpu']['max']}%

【负载分布】
- 低负载: {report_details['load_distribution'].get('low', '0%')}
- 中负载: {report_details['load_distribution'].get('medium', '0%')}
- 高负载: {report_details['load_distribution'].get('high', '0%')}
- 临界: {report_details['load_distribution'].get('critical', '0%')}

请输出：
1. 运维摘要（1-2句）
2. 风险评估（当前系统稳定性评估）
3. 改进建议（3-5条，如无则说明"保持当前配置"）"""

        llm_result = await self._call_llm_for_analysis(system_prompt, user_prompt)

        if llm_result:
            summary, llm_recommendations = self._parse_llm_analysis(llm_result)
            recommendations = llm_recommendations if llm_recommendations else rule_recommendations
            confidence = 0.85
        else:
            summary = f"过去 {total_samples} 个采样点，平均 VRAM: {report_details['vram']['avg']:.1%}"
            recommendations = rule_recommendations
            confidence = 0.9

        analysis = ResourceAnalysis(
            timestamp=datetime.now().isoformat(),
            analysis_type="report",
            summary=summary,
            details=report_details,
            recommendations=recommendations,
            confidence=confidence,
        )

        self._last_analysis = analysis
        self._analysis_history.append(analysis)
        return analysis

    # ------------------------------------------------------------------
    # LLM 响应解析
    # ------------------------------------------------------------------

    def _parse_llm_analysis(self, llm_response: str) -> Tuple[str, List[str]]:
        """从 LLM 响应中提取摘要和建议

        Args:
            llm_response: LLM 原始响应文本

        Returns:
            (summary, recommendations) 元组
        """
        lines = llm_response.strip().split("\n")
        summary = ""
        recommendations = []

        in_recommendations = False
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检测"建议"/"推荐"部分
            lower = line.lower()
            if any(kw in lower for kw in ["建议", "推荐", "改进", "优化建议", "修复建议"]):
                in_recommendations = True
                continue

            # 检测"总结"/"摘要"部分
            if any(kw in lower for kw in ["总结", "摘要", "评估", "根因", "风险", "趋势"]):
                in_recommendations = False
                continue

            if in_recommendations:
                # 去掉编号前缀 (1. 2. - * 等)
                cleaned = line.lstrip("0123456789. -*)>#")
                if len(cleaned) > 3:
                    recommendations.append(cleaned)
            elif not summary:
                # 第一段非标题文本作为摘要
                if len(line) > 10 and not line.startswith("#"):
                    summary = line
                else:
                    # 可能是多行摘要
                    pass

        # 如果没解析出摘要，用整个响应的前200字符
        if not summary:
            summary = llm_response.strip()[:200]

        # 如果没解析出建议列表，尝试按编号行提取
        if not recommendations:
            for line in lines:
                stripped = line.strip()
                if stripped and (stripped[0].isdigit() or stripped.startswith("- ")):
                    cleaned = stripped.lstrip("0123456789. -*)>#")
                    if len(cleaned) > 3:
                        recommendations.append(cleaned)

        return summary, recommendations

    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------

    def get_last_analysis(self) -> Optional[ResourceAnalysis]:
        """获取最后一次分析结果"""
        return self._last_analysis

    def get_analysis_history(self, limit: int = 10) -> List[ResourceAnalysis]:
        """获取分析历史"""
        return self._analysis_history[-limit:]


# 全局单例
resource_analyzer = ResourceAnalyzer()
