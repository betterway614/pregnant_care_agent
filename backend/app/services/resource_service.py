"""资源管理服务 - 整合资源监控与资源规则引擎"""

import threading
from typing import List, Optional

from loguru import logger

from ..core.resource_monitor import resource_monitor, ResourceState
from ..core.resource_rules import resource_rule_engine, AcceleratorType
from ..core.resource_analyzer import resource_analyzer


class ResourceService:
    """资源管理服务 - 单例模式

    整合 ResourceMonitor 和 ResourceRuleEngine，
    提供统一的资源状态查询、策略管理和配置更新接口。
    """

    _instance: Optional["ResourceService"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._monitor = resource_monitor
        self._rule_engine = resource_rule_engine
        self._analyzer = resource_analyzer
        logger.info("ResourceService 初始化完成")

    # ------------------------------------------------------------------
    # 系统状态
    # ------------------------------------------------------------------

    def get_system_status(self) -> dict:
        """获取系统资源状态摘要

        Returns:
            包含当前资源状态、负载级别、策略信息和历史记录数量的字典。
        """
        state = self._monitor.get_current_state()
        load_level = self._monitor.get_load_level(state)
        policy = self._rule_engine.get_policy()

        return {
            "state": state.to_dict(),
            "load_level": load_level.value,
            "policy": policy.to_dict(),
            "history_count": len(self._monitor._history),
        }

    # ------------------------------------------------------------------
    # 服务配置
    # ------------------------------------------------------------------

    def get_service_configs(self) -> dict:
        """获取所有服务的当前资源配置

        Returns:
            以服务名称为键、配置字典为值的字典。
        """
        return {
            name: config.to_dict()
            for name, config in self._rule_engine.services.items()
        }

    def update_service_config(self, service_name: str, **kwargs) -> bool:
        """更新指定服务的资源配置

        Args:
            service_name: 服务名称 (llm / bge_m3 / tts / asr)。
            **kwargs: 可更新的字段，包括 batch_size, accelerator, priority。

        Returns:
            更新是否成功。
        """
        success = self._rule_engine.update_service_config(service_name, **kwargs)
        if success:
            logger.info("服务 {} 配置已更新: {}", service_name, kwargs)
        else:
            logger.warning("服务 {} 配置更新失败: {}", service_name, kwargs)
        return success

    # ------------------------------------------------------------------
    # 策略管理
    # ------------------------------------------------------------------

    def set_policy(self, policy_name: str) -> bool:
        """设置资源分配策略

        Args:
            policy_name: 策略名称 (performance / balanced / conservative / llm_priority)。

        Returns:
            设置是否成功。
        """
        success = self._rule_engine.set_policy(policy_name)
        if success:
            logger.info("资源策略已切换到: {}", policy_name)
        else:
            logger.warning("未知资源策略: {}", policy_name)
        return success

    # ------------------------------------------------------------------
    # 优化建议
    # ------------------------------------------------------------------

    def get_adjustments(self) -> List[dict]:
        """根据当前资源状态获取服务配置优化建议

        Returns:
            包含每个服务当前配置、最优配置和变更列表的摘要列表。
        """
        state = self._monitor.get_current_state()
        return self._rule_engine.get_adjustments_summary(state)

    # ------------------------------------------------------------------
    # 后台监控
    # ------------------------------------------------------------------

    def start_monitoring(self, interval: float = 5.0):
        """启动后台资源监控

        Args:
            interval: 采样间隔，单位秒，默认 5 秒。
        """
        self._monitor.start_monitoring(interval)
        logger.info("后台资源监控已启动 (间隔: {}s)", interval)

    def stop_monitoring(self):
        """停止后台资源监控"""
        self._monitor.stop_monitoring()
        logger.info("后台资源监控已停止")

    # ------------------------------------------------------------------
    # 历史数据
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 100) -> List[dict]:
        """获取资源监控历史数据

        Args:
            limit: 返回的记录条数上限，默认 100。

        Returns:
            历史资源状态字典列表，按时间升序排列。
        """
        history = self._monitor.get_history(limit)
        return [state.to_dict() for state in history]

    # ------------------------------------------------------------------
    # LLM 智能分析 (P3)
    # ------------------------------------------------------------------

    async def get_llm_analysis(self, analysis_type: str = "pattern") -> dict:
        """获取 LLM 智能分析结果

        Args:
            analysis_type: 分析类型
                - "pattern": 使用模式分析
                - "anomaly": 异常诊断
                - "optimization": 优化建议
                - "report": 每日报告

        Returns:
            分析结果字典。
        """
        if analysis_type == "pattern":
            result = await self._analyzer.analyze_usage_pattern()
        elif analysis_type == "anomaly":
            state = self._monitor.get_current_state()
            result = await self._analyzer.diagnose_anomaly(state)
        elif analysis_type == "optimization":
            result = await self._analyzer.generate_optimization_report()
        elif analysis_type == "report":
            result = await self._analyzer.generate_daily_report()
        else:
            return {
                "error": f"未知分析类型: {analysis_type}",
                "supported_types": ["pattern", "anomaly", "optimization", "report"],
            }

        return result.to_dict()

    def get_last_analysis(self) -> Optional[dict]:
        """获取最后一次分析结果"""
        analysis = self._analyzer.get_last_analysis()
        return analysis.to_dict() if analysis else None

    def get_analysis_history(self, limit: int = 10) -> List[dict]:
        """获取分析历史"""
        return [a.to_dict() for a in self._analyzer.get_analysis_history(limit)]


# 全局单例
resource_service = ResourceService()
