"""
正式状态机 — 集中定义所有状态转换

替代散布在 trigger_followup、respond_to_followup、
confirm_record、sign_record 中的 ad-hoc if 检查。

遵循 SRP: 状态转换逻辑集中在此模块。
遵循 OCP: 新增状态/转换只需调用 add()，无需修改已有代码。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class FollowUpStatus(str, Enum):
    """随访记录状态"""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CONFIRMED = "confirmed"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


@dataclass
class Transition:
    """状态转换定义"""
    source: FollowUpStatus
    target: FollowUpStatus
    trigger: str
    guard: Optional[Callable[[dict], bool]] = None
    action: Optional[Callable[[dict], None]] = None


class InvalidTransition(Exception):
    """无效的状态转换"""
    pass


class FollowUpStateMachine:
    """随访记录状态机"""

    def __init__(self) -> None:
        self._transitions: list[Transition] = []

    def add(
        self,
        source: FollowUpStatus,
        target: FollowUpStatus,
        trigger: str,
        guard: Optional[Callable[[dict], bool]] = None,
        action: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """注册状态转换"""
        self._transitions.append(Transition(source, target, trigger, guard, action))

    def can_transition(self, current: FollowUpStatus, trigger: str, ctx: dict | None = None) -> bool:
        """检查是否可以执行转换"""
        ctx = ctx or {}
        for t in self._transitions:
            if t.source == current and t.trigger == trigger:
                return t.guard is None or t.guard(ctx)
        return False

    def transition(self, current: FollowUpStatus, trigger: str, ctx: dict | None = None) -> FollowUpStatus:
        """执行状态转换

        Args:
            current: 当前状态
            trigger: 触发事件
            ctx: 上下文信息（传递给 guard 和 action）

        Returns:
            新状态

        Raises:
            InvalidTransition: 转换无效时
        """
        ctx = ctx or {}
        for t in self._transitions:
            if t.source == current and t.trigger == trigger:
                if t.guard and not t.guard(ctx):
                    raise InvalidTransition(
                        f"Guard 检查失败: {current.value} --{trigger}--> {t.target.value}"
                    )
                if t.action:
                    t.action(ctx)
                return t.target

        allowed = self.allowed_triggers(current)
        raise InvalidTransition(
            f"无效转换: {current.value} --{trigger}--> ? (允许的触发: {allowed})"
        )

    def allowed_triggers(self, current: FollowUpStatus) -> list[str]:
        """获取当前状态允许的所有触发"""
        return [t.trigger for t in self._transitions if t.source == current]


# ==================== 全局状态机实例 ====================

followup_fsm = FollowUpStateMachine()

# 注册所有合法转换
followup_fsm.add(FollowUpStatus.DRAFT, FollowUpStatus.IN_PROGRESS, "start")
followup_fsm.add(FollowUpStatus.DRAFT, FollowUpStatus.DRAFT, "edit")  # 护士编辑草稿
followup_fsm.add(FollowUpStatus.IN_PROGRESS, FollowUpStatus.IN_PROGRESS, "edit")  # 护士编辑进行中记录
followup_fsm.add(FollowUpStatus.IN_PROGRESS, FollowUpStatus.COMPLETED, "complete")
followup_fsm.add(FollowUpStatus.COMPLETED, FollowUpStatus.CONFIRMED, "confirm")
followup_fsm.add(FollowUpStatus.COMPLETED, FollowUpStatus.DRAFT, "reject")  # 驳回重做
followup_fsm.add(FollowUpStatus.CONFIRMED, FollowUpStatus.ARCHIVED, "archive")
followup_fsm.add(FollowUpStatus.DRAFT, FollowUpStatus.CANCELLED, "cancel")  # 取消草稿（去重/主动取消）
followup_fsm.add(FollowUpStatus.IN_PROGRESS, FollowUpStatus.CANCELLED, "cancel")  # 取消进行中的随访
