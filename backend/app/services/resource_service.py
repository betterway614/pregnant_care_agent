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
    启动时自动检测各服务的实际运行状态。
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
        # 启动时自动检测服务实际状态
        self._auto_detect_services()
        logger.info("ResourceService 初始化完成")

    def _auto_detect_services(self):
        """自动检测各服务的实际运行状态，更新配置

        健壮性保证：
        - 服务离线时（端口不可达）静默保留原配置，不抛错
        - 启动时最多等待 3 秒（4 服务 × socket 检测 + 1s HTTP）
        - 不覆盖用户通过 settings 显式配置的值
        - 服务地址可通过 resource_*_host 配置（SSH 端口转发场景）

        注意: SSH 端口转发场景下，后端监听的 127.0.0.1:port 实际是远程服务
        （通过 SSH 隧道映射过来），检测本地端口即可。
        如果服务部署在不同机器，需通过 resource_*_host 配置远程地址。
        """
        import socket
        from ..config import settings

        detectors = {
            "llm": self._detect_llm,
            "bge_m3": self._detect_embedding,
            "tts": self._detect_tts,
            "asr": self._detect_asr,
        }

        for service_name, detector in detectors.items():
            try:
                config = self._rule_engine.services.get(service_name)
                if not config:
                    continue
                host = getattr(settings, f"resource_{service_name}_host", "127.0.0.1")
                port = config.port
                # 快速 socket 检测端口是否开放，避免长时间 HTTP 超时
                if not self._is_port_open(host, port, timeout=0.5):
                    continue
                result = detector()
                if not result:
                    continue
                # 不覆盖用户通过 settings 显式配置的值
                if self._is_user_configured(service_name):
                    continue
                old_accel = config.accelerator.value
                new_accel = result.get("accelerator")
                if new_accel and new_accel != old_accel:
                    config.accelerator = AcceleratorType(new_accel)
                    logger.info(f"服务 {service_name} 加速器自动检测: {old_accel} -> {new_accel}")
            except Exception as e:
                # 静默失败，不影响启动
                logger.debug(f"服务 {service_name} 自动检测失败: {e}")

    def _is_port_open(self, host: str, port: int, timeout: float = 0.5) -> bool:
        """快速检测端口是否开放（避免 HTTP 超时阻塞启动）"""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                return s.connect_ex((host, port)) == 0
        except Exception:
            return False

    def _is_user_configured(self, service_name: str) -> bool:
        """检查用户是否通过 settings 显式配置了该服务的加速器"""
        try:
            from ..config import settings
            val = getattr(settings, f"resource_{service_name}_accel", "")
            return val in ("cpu", "gpu", "npu")
        except Exception:
            return False

    def _detect_llm(self) -> Optional[dict]:
        """检测 LLM 服务状态（vLLM/SGLang/Ollama）"""
        import requests
        from ..config import settings
        host = settings.resource_llm_host
        port = self._rule_engine.services["llm"].port
        # 尝试 vLLM/SGLang API
        try:
            resp = requests.get(f"http://{host}:{port}/v1/models", timeout=1)
            if resp.ok:
                return {"accelerator": "gpu"}
        except Exception:
            pass
        # 尝试 Ollama API
        try:
            resp = requests.get(f"http://{host}:{port}/api/ps", timeout=1)
            if resp.ok:
                return {"accelerator": "gpu"}
        except Exception:
            pass
        return None

    def _detect_embedding(self) -> Optional[dict]:
        """检测 Embedding 服务状态"""
        import requests
        from ..config import settings
        host = settings.resource_bge_m3_host
        port = self._rule_engine.services["bge_m3"].port
        # 优先查询 /device 端点获取精确设备
        try:
            resp = requests.get(f"http://{host}:{port}/device", timeout=1)
            if resp.ok:
                data = resp.json()
                device = data.get("device", "").lower()
                if "cpu" in device:
                    return {"accelerator": "cpu"}
                if "npu" in device or "xdna" in device:
                    return {"accelerator": "npu"}
                if "cuda" in device or "gpu" in device or "rocm" in device:
                    return {"accelerator": "gpu"}
        except Exception:
            pass
        # 回退到 /health 端点
        try:
            resp = requests.get(f"http://{host}:{port}/health", timeout=1)
            if resp.ok:
                return {"accelerator": "gpu"}
        except Exception:
            pass
        return None

    def _detect_tts(self) -> Optional[dict]:
        """检测 TTS 服务状态"""
        import requests
        from ..config import settings
        host = settings.resource_tts_host
        port = self._rule_engine.services["tts"].port
        try:
            resp = requests.get(f"http://{host}:{port}/health", timeout=1)
            if resp.ok:
                return {"accelerator": "gpu"}
        except Exception:
            pass
        return None

    def _detect_asr(self) -> Optional[dict]:
        """检测 ASR 服务状态"""
        import requests
        from ..config import settings
        host = settings.resource_asr_host
        port = self._rule_engine.services["asr"].port
        try:
            resp = requests.get(f"http://{host}:{port}/", timeout=1)
            if resp.ok:
                return {"accelerator": "npu"}
        except Exception:
            pass
        return None

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
