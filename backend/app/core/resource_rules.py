"""
资源规则引擎 - 基于规则的动态资源分配决策

提供可靠的、可测试的资源分配策略，不依赖 LLM。
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, List
from enum import Enum

from .resource_monitor import ResourceState, LoadLevel

logger = logging.getLogger(__name__)


class AcceleratorType(str, Enum):
    """加速器类型"""
    GPU = "gpu"
    NPU = "npu"
    CPU = "cpu"


class PolicyType(str, Enum):
    """策略类型"""
    PERFORMANCE = "performance"    # 性能优先
    BALANCED = "balanced"          # 平衡模式
    CONSERVATIVE = "conservative"  # 保守模式
    LLM_PRIORITY = "llm_priority" # LLM 优先


@dataclass
class ServiceResourceConfig:
    """服务资源配置"""
    name: str
    port: int
    accelerator: AcceleratorType
    batch_size: int
    min_batch_size: int
    max_batch_size: int
    priority: int  # 1-10, 10 最高
    can_offload_to_cpu: bool = True
    can_offload_to_npu: bool = False
    current_load: float = 0.0  # 当前负载百分比

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "port": self.port,
            "accelerator": self.accelerator.value,
            "batch_size": self.batch_size,
            "min_batch_size": self.min_batch_size,
            "max_batch_size": self.max_batch_size,
            "priority": self.priority,
            "can_offload_to_cpu": self.can_offload_to_cpu,
            "can_offload_to_npu": self.can_offload_to_npu,
            "current_load": self.current_load,
        }


@dataclass
class ResourcePolicy:
    """资源分配策略"""
    name: str
    description: str
    vram_threshold_high: float = 0.85
    vram_threshold_critical: float = 0.95
    gpu_threshold_high: float = 0.90
    enable_npu_offload: bool = True
    enable_cpu_offload: bool = True
    enable_batch_adjustment: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name.value if isinstance(self.name, PolicyType) else self.name,
            "description": self.description,
            "vram_threshold_high": self.vram_threshold_high,
            "vram_threshold_critical": self.vram_threshold_critical,
            "gpu_threshold_high": self.gpu_threshold_high,
            "enable_npu_offload": self.enable_npu_offload,
            "enable_cpu_offload": self.enable_cpu_offload,
            "enable_batch_adjustment": self.enable_batch_adjustment,
        }


class ResourceRuleEngine:
    """资源规则引擎"""

    def __init__(self):
        # 支持从 settings 覆盖加速器类型: resource_llm_accel, resource_bge_m3_accel, etc.
        def _get_accel(service_name: str, default: AcceleratorType) -> AcceleratorType:
            try:
                from ..config import settings
                val = getattr(settings, f"resource_{service_name}_accel", "").lower()
                if val in ("cpu", "gpu", "npu"):
                    return AcceleratorType(val)
            except Exception:
                pass
            return default

        # 默认服务配置（支持环境变量覆盖）
        self.services: Dict[str, ServiceResourceConfig] = {
            "llm": ServiceResourceConfig(
                name="LLM (Qwen3.6 Q4)",
                port=8080,
                accelerator=_get_accel("llm", AcceleratorType.GPU),
                batch_size=4,
                min_batch_size=1,
                max_batch_size=8,
                priority=10,
                can_offload_to_cpu=False,
                can_offload_to_npu=False,
            ),
            "bge_m3": ServiceResourceConfig(
                name="BGE-M3 (Embedding)",
                port=8081,
                accelerator=_get_accel("bge_m3", AcceleratorType.GPU),
                batch_size=64,
                min_batch_size=8,
                max_batch_size=256,
                priority=7,
                can_offload_to_cpu=True,
                can_offload_to_npu=False,
            ),
            "tts": ServiceResourceConfig(
                name="TTS (CosyVoice2)",
                port=9880,
                accelerator=_get_accel("tts", AcceleratorType.GPU),
                batch_size=4,
                min_batch_size=1,
                max_batch_size=16,
                priority=6,
                can_offload_to_cpu=True,
                can_offload_to_npu=False,
            ),
            "asr": ServiceResourceConfig(
                name="ASR (FunASR)",
                port=10096,
                accelerator=_get_accel("asr", AcceleratorType.NPU),
                batch_size=4,
                min_batch_size=1,
                max_batch_size=16,
                priority=5,
                can_offload_to_cpu=True,
                can_offload_to_npu=True,
            ),
        }

        # 预设策略
        self.policies: Dict[str, ResourcePolicy] = {
            PolicyType.PERFORMANCE: ResourcePolicy(
                name=PolicyType.PERFORMANCE,
                description="性能优先: 所有服务使用 GPU，高批处理大小",
                vram_threshold_high=0.90,
                vram_threshold_critical=0.98,
                enable_npu_offload=False,
                enable_cpu_offload=False,
                enable_batch_adjustment=True,
            ),
            PolicyType.BALANCED: ResourcePolicy(
                name=PolicyType.BALANCED,
                description="平衡模式: ASR 使用 NPU，其他 GPU",
                vram_threshold_high=0.85,
                vram_threshold_critical=0.95,
                enable_npu_offload=True,
                enable_cpu_offload=True,
                enable_batch_adjustment=True,
            ),
            PolicyType.CONSERVATIVE: ResourcePolicy(
                name=PolicyType.CONSERVATIVE,
                description="保守模式: VRAM 紧张时积极卸载",
                vram_threshold_high=0.75,
                vram_threshold_critical=0.90,
                enable_npu_offload=True,
                enable_cpu_offload=True,
                enable_batch_adjustment=True,
            ),
            PolicyType.LLM_PRIORITY: ResourcePolicy(
                name=PolicyType.LLM_PRIORITY,
                description="LLM 优先: 其他服务让步给 LLM",
                vram_threshold_high=0.70,
                vram_threshold_critical=0.85,
                enable_npu_offload=True,
                enable_cpu_offload=True,
                enable_batch_adjustment=True,
            ),
        }

        self.current_policy = PolicyType.BALANCED

    def set_policy(self, policy_name: str) -> bool:
        """设置当前策略"""
        if policy_name in self.policies:
            self.current_policy = PolicyType(policy_name)
            logger.info("资源策略切换到: {}", policy_name)
            return True
        logger.warning("未知策略: {}", policy_name)
        return False

    def get_policy(self) -> ResourcePolicy:
        """获取当前策略"""
        return self.policies[self.current_policy]

    def update_service_config(self, service_name: str, **kwargs) -> bool:
        """更新服务配置"""
        if service_name not in self.services:
            return False

        config = self.services[service_name]

        if "batch_size" in kwargs:
            new_batch = kwargs["batch_size"]
            config.batch_size = max(config.min_batch_size, min(config.max_batch_size, new_batch))

        if "accelerator" in kwargs:
            try:
                config.accelerator = AcceleratorType(kwargs["accelerator"])
            except ValueError:
                logger.warning("无效的加速器类型: {}", kwargs["accelerator"])
                return False

        if "priority" in kwargs:
            config.priority = max(1, min(10, kwargs["priority"]))

        logger.info("服务 {} 配置已更新: {}", service_name, kwargs)
        return True

    def calculate_optimal_config(self, state: ResourceState) -> Dict[str, ServiceResourceConfig]:
        """根据当前状态计算最优配置"""
        policy = self.get_policy()
        load_level = self._get_load_level(state, policy)

        # 创建配置副本
        adjustments: Dict[str, ServiceResourceConfig] = {}

        # 按优先级排序服务
        sorted_services = sorted(
            self.services.items(),
            key=lambda x: x[1].priority,
            reverse=True,
        )

        remaining_vram = state.vram_free_gb

        for name, config in sorted_services:
            # LLM 不调整
            if name == "llm":
                adjustments[name] = ServiceResourceConfig(
                    name=config.name,
                    port=config.port,
                    accelerator=config.accelerator,
                    batch_size=config.batch_size,
                    min_batch_size=config.min_batch_size,
                    max_batch_size=config.max_batch_size,
                    priority=config.priority,
                    can_offload_to_cpu=config.can_offload_to_cpu,
                    can_offload_to_npu=config.can_offload_to_npu,
                    current_load=config.current_load,
                )
                continue

            new_config = ServiceResourceConfig(
                name=config.name,
                port=config.port,
                accelerator=config.accelerator,
                batch_size=config.batch_size,
                min_batch_size=config.min_batch_size,
                max_batch_size=config.max_batch_size,
                priority=config.priority,
                can_offload_to_cpu=config.can_offload_to_cpu,
                can_offload_to_npu=config.can_offload_to_npu,
                current_load=config.current_load,
            )

            # 根据负载级别调整
            if load_level == LoadLevel.CRITICAL:
                # 紧急模式: 积极卸载
                if policy.enable_cpu_offload and config.can_offload_to_cpu:
                    new_config.accelerator = AcceleratorType.CPU
                    new_config.batch_size = config.min_batch_size
                    logger.warning("[CRITICAL] {} 卸载到 CPU", name)

            elif load_level == LoadLevel.HIGH:
                # 高负载: 降低批处理，考虑 NPU
                if policy.enable_batch_adjustment:
                    new_config.batch_size = max(
                        config.min_batch_size,
                        config.batch_size // 2,
                    )

                if policy.enable_npu_offload and config.can_offload_to_npu:
                    new_config.accelerator = AcceleratorType.NPU
                    logger.info("[HIGH] {} 切换到 NPU", name)

            elif load_level == LoadLevel.MEDIUM:
                # 中等负载: 适度调整
                if policy.enable_batch_adjustment:
                    new_config.batch_size = max(
                        config.min_batch_size,
                        int(config.batch_size * 0.75),
                    )

            else:
                # 低负载: 恢复默认或增加批处理
                if policy.enable_batch_adjustment:
                    new_config.batch_size = min(
                        config.max_batch_size,
                        int(config.batch_size * 1.25),
                    )

            adjustments[name] = new_config

        return adjustments

    def get_adjustments_summary(self, state: ResourceState) -> List[dict]:
        """获取调整摘要（用于前端展示）"""
        optimal = self.calculate_optimal_config(state)
        summary = []

        for name, config in optimal.items():
            current = self.services[name]
            changes = []

            if config.batch_size != current.batch_size:
                changes.append(f"batch_size: {current.batch_size} → {config.batch_size}")

            if config.accelerator != current.accelerator:
                changes.append(f"accelerator: {current.accelerator.value} → {config.accelerator.value}")

            summary.append({
                "service": name,
                "name": config.name,
                "current": current.to_dict(),
                "optimal": config.to_dict(),
                "changes": changes,
                "needs_update": len(changes) > 0,
            })

        return summary

    def _get_load_level(self, state: ResourceState, policy: ResourcePolicy) -> LoadLevel:
        """获取负载级别"""
        if state.vram_percent >= policy.vram_threshold_critical:
            return LoadLevel.CRITICAL
        elif state.vram_percent >= policy.vram_threshold_high:
            return LoadLevel.HIGH
        elif state.vram_percent >= 0.50:
            return LoadLevel.MEDIUM
        else:
            return LoadLevel.LOW

    def to_dict(self) -> dict:
        """导出为字典"""
        return {
            "current_policy": self.current_policy.value,
            "policies": {name: p.to_dict() for name, p in self.policies.items()},
            "services": {name: s.to_dict() for name, s in self.services.items()},
        }


# 全局单例
resource_rule_engine = ResourceRuleEngine()
