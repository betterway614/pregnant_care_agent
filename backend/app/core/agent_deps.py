"""
Agno Agent 依赖注入桥接层

将 DI 容器中的服务注入到 Agent 的 dependencies dict，
使 @tool 函数可以通过 run_context.dependencies 访问服务实例。

用法:
    from .agent_deps import build_agent_dependencies
    agent = Agent(..., dependencies=build_agent_dependencies())
"""
from __future__ import annotations

from typing import Any


def build_agent_dependencies() -> dict[str, Any]:
    """构建 Agent(dependencies={...}) 所需的字典

    在 Agent 创建时调用，将仓储和服务实例注入到 RunContext.dependencies。
    工具函数通过 run_context.dependencies["patient_repo"] 获取实例。
    """
    from ..container import container
    from ..interfaces.repositories import PatientRepository, AlertRepository

    deps: dict[str, Any] = {}
    try:
        deps["patient_repo"] = container.resolve(PatientRepository)
    except Exception:
        pass
    try:
        deps["alert_repo"] = container.resolve(AlertRepository)
    except Exception:
        pass
    return deps
