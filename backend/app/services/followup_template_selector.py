"""
随访模板选择器 — 规则表替代 if/elif 链

遵循 OCP: 新增模板只需添加 TemplateRule 并调用 register_template_rule()，
无需修改 select_template 函数。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TemplateRule:
    """模板选择规则"""
    template_id: str
    priority: int
    risk_tag: Optional[str] = None
    gest_week_min: int = 0
    gest_week_max: int = 45

    def matches(self, risk_tags: list[str], gest_week: int) -> bool:
        """检查规则是否匹配"""
        if self.risk_tag and self.risk_tag not in risk_tags:
            return False
        if not (self.gest_week_min <= gest_week <= self.gest_week_max):
            return False
        return True


# 规则表（按优先级排序，高优先级先匹配）
_TEMPLATE_RULES: list[TemplateRule] = [
    TemplateRule("fgr_high_risk",   priority=100, risk_tag="FGR"),
    TemplateRule("gdm",             priority=90,  risk_tag="GDM"),
    TemplateRule("hypertension",    priority=90,  risk_tag="HYPERTENSION"),
    TemplateRule("mental_health",   priority=80,  risk_tag="MENTAL_HEALTH"),
    TemplateRule("post_discharge",  priority=70,  risk_tag="POST_DISCHARGE"),
    TemplateRule("early_pregnancy", priority=50,  gest_week_min=0, gest_week_max=12),
    TemplateRule("late_pregnancy",  priority=50,  gest_week_min=28, gest_week_max=45),
    TemplateRule("standard",        priority=0),
]


def register_template_rule(rule: TemplateRule) -> None:
    """注册新的模板选择规则"""
    _TEMPLATE_RULES.append(rule)
    _TEMPLATE_RULES.sort(key=lambda r: r.priority, reverse=True)


def select_template(risk_tags: list[str], gest_week: int) -> tuple[str, dict]:
    """选择最匹配的随访模板

    Args:
        risk_tags: 风险标签列表
        gest_week: 孕周

    Returns:
        (template_id, template_dict)
    """
    from .followup_service import FOLLOWUP_TEMPLATES

    for rule in _TEMPLATE_RULES:
        if rule.matches(risk_tags, gest_week):
            template = FOLLOWUP_TEMPLATES.get(rule.template_id, FOLLOWUP_TEMPLATES.get("standard"))
            return rule.template_id, template

    return "standard", FOLLOWUP_TEMPLATES.get("standard", {})
