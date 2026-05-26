"""高危规则引擎 - CPU执行"""
import re
import operator
from typing import Callable
from datetime import datetime


# 安全的比较运算符映射
OPERATORS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
}

# 安全的逻辑运算符
LOGICAL_OPS = {"and", "or", "not"}


def _safe_eval_condition(condition: str, variables: dict) -> bool:
    """安全评估条件表达式，不使用 eval()

    支持的语法：
    - 比较: sbp >= 140, dbp < 60
    - 逻辑: and, or, not
    - 复合: sbp >= 140 or dbp >= 90
    """
    try:
        # 分割 by and/or
        condition = condition.strip()

        # 处理 "or" 逻辑
        if " or " in condition:
            parts = condition.split(" or ")
            return any(_safe_eval_condition(part.strip(), variables) for part in parts)

        # 处理 "and" 逻辑
        if " and " in condition:
            parts = condition.split(" and ")
            return all(_safe_eval_condition(part.strip(), variables) for part in parts)

        # 处理 "not" 逻辑
        if condition.startswith("not "):
            return not _safe_eval_condition(condition[4:].strip(), variables)

        # 解析比较表达式: variable operator value
        for op_str, op_func in OPERATORS.items():
            if op_str in condition:
                left, right = condition.split(op_str, 1)
                left = left.strip()
                right = right.strip()

                # 获取左操作数的值
                left_value = variables.get(left)
                if left_value is None:
                    return False

                # 解析右操作数（可能是数字或变量）
                try:
                    right_value = float(right)
                except ValueError:
                    right_value = variables.get(right)
                    if right_value is None:
                        return False

                return op_func(left_value, right_value)

        return False
    except Exception:
        return False


class Rule:
    """规则定义"""
    def __init__(self, rule_id: str, domain: str, priority: int,
                 expression: str, level: str,
                 message: str, action: str = "ALERT_NURSE"):
        self.id = rule_id
        self.domain = domain      # vital / fetal / mental
        self.priority = priority  # 组内优先级, 数字越大越高
        self.expression = expression
        self.level = level
        self.message = message
        self.action = action

    def evaluate(self, context: dict) -> bool:
        """评估规则是否命中（安全版本，不使用eval）"""
        try:
            variables = {
                "sbp": context.get("sbp"),  # None if not measured
                "dbp": context.get("dbp"),  # None if not measured
                "weight": context.get("weight", 0) or 0,
                "fetal_movement": context.get("fetal_movement", 0) or 0,
                "fetal_movement_avg": context.get("fetal_movement_avg", context.get("fetal_movement", 0)) or context.get("fetal_movement", 0),
                "fetal_drop_threshold": (context.get("fetal_movement_avg", context.get("fetal_movement", 0)) or context.get("fetal_movement", 0)) * 0.5,
                "weight_gain_weekly": context.get("weight_gain_weekly"),  # None if not computed
                "emotion_score": context.get("emotion_score_avg_7d"),  # None if not available
                "emotion_score_avg_7d": context.get("emotion_score_avg_7d", 0) or 0,
                "blood_sugar_fasting": context.get("blood_sugar_fasting", 0) or 0,
                "blood_sugar_postprandial": context.get("blood_sugar_postprandial", 0) or 0,
                "sleep_hours": context.get("sleep_hours", 8) or 8,
                "gest_week": context.get("gest_week", 0) or 0,
            }
            return _safe_eval_condition(self.expression, variables)
        except Exception:
            return False


# 规则定义
RULES = [
    # === 生命体征 (vital) ===
    Rule("RULE_BP_HIGH", "vital", 3, "sbp >= 140 or dbp >= 90", "RED",
         "血压异常升高（≥140/90mmHg）", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_BP_HIGH_ORANGE", "vital", 2, "sbp >= 135 or dbp >= 85", "ORANGE",
         "血压偏高（≥135/85mmHg），需要关注", "ALERT_NURSE"),
    Rule("RULE_BP_LOW", "vital", 1, "sbp < 90 or dbp < 60", "YELLOW",
         "血压偏低，需关注", "NOTE_NURSE"),
    Rule("RULE_LATE_PREGNANCY_BP", "vital", 2, "sbp >= 130 and gest_week >= 32", "ORANGE",
         "孕晚期血压偏高，子痫前期风险", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_BS_POSTPRANDIAL_HIGH", "vital", 3, "blood_sugar_postprandial > 7.0", "RED",
         "餐后血糖异常（>7.0mmol/L）", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_BS_FASTING_HIGH", "vital", 2, "blood_sugar_fasting > 5.3", "ORANGE",
         "空腹血糖偏高（>5.3mmol/L），建议复查", "ALERT_NURSE"),
    Rule("RULE_WEIGHT_GAIN_FAST", "vital", 2, "weight_gain_weekly > 2.0", "ORANGE",
         "体重周增长过快（>2kg/周）", "ALERT_NURSE"),
    Rule("RULE_WEIGHT_GAIN_SLOW", "vital", 1, "weight_gain_weekly < 0.1 and gest_week > 16", "YELLOW",
         "体重增长过慢，需关注营养摄入", "NOTE_NURSE"),

    # === 胎儿 (fetal) ===
    Rule("RULE_FETAL_DROP", "fetal", 3, "fetal_movement < fetal_drop_threshold", "RED",
         "胎动显著减少（低于平均50%）", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_FETAL_VERY_LOW", "fetal", 3, "fetal_movement < 3", "RED",
         "胎动极少（<3次/小时），请立即就医", "ALERT_NURSE_AND_DOCTOR"),

    # === 心理行为 (mental) ===
    Rule("RULE_EMOTION_CRITICAL", "mental", 3, "emotion_score_avg_7d <= 1.0", "RED",
         "近7日情绪评分持续极低（平均≤1.0分），需立即心理干预", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_EMOTION_HIGH", "mental", 2, "emotion_score_avg_7d <= 1.5", "ORANGE",
         "近7日情绪评分持续偏低（平均≤1.5分），建议心理干预", "ALERT_NURSE"),
    Rule("RULE_SLEEP_SHORT", "mental", 1, "sleep_hours < 4", "YELLOW",
         "睡眠严重不足（<4小时），建议改善睡眠", "NOTE_NURSE"),
]


class RuleEngine:
    """规则引擎"""

    def __init__(self):
        self.rules = RULES

    def evaluate_all(self, context: dict) -> list[dict]:
        """每个领域只返回优先级最高的命中。同领域同优先级合并 triggered_rules。"""
        domain_hits: dict[str, dict] = {}
        for rule in self.rules:
            if rule.evaluate(context):
                current = domain_hits.get(rule.domain)
                if not current or rule.priority > current["priority"]:
                    domain_hits[rule.domain] = {
                        "rule_id": rule.id,
                        "domain": rule.domain,
                        "priority": rule.priority,
                        "level": rule.level,
                        "message": rule.message,
                        "action": rule.action,
                        "triggered_rules": [rule.id],
                    }
                elif rule.priority == current["priority"]:
                    current["triggered_rules"].append(rule.id)
        return list(domain_hits.values())

    def evaluate_fgr_risk(self, risk_level: str) -> list[dict]:
        """FGR风险等级触发规则"""
        alerts = []
        if risk_level == "critical":
            alerts.append({
                "rule_id": "FGR_CRITICAL_RISK",
                "domain": "fetal",
                "level": "RED",
                "message": "FGR评估结果: 极高风险",
                "action": "ALERT_DOCTOR",
            })
        elif risk_level == "high":
            alerts.append({
                "rule_id": "FGR_HIGH_RISK",
                "domain": "fetal",
                "level": "ORANGE",
                "message": "FGR评估结果: 高风险",
                "action": "ALERT_DOCTOR",
            })
        elif risk_level == "medium":
            alerts.append({
                "rule_id": "FGR_MEDIUM_RISK",
                "domain": "fetal",
                "level": "YELLOW",
                "message": "FGR评估结果: 中风险",
                "action": "ALERT_NURSE",
            })
        return alerts


# 全局单例
rule_engine = RuleEngine()

# 规则元数据映射（用于数据修复）
RULE_META_MAP: dict[str, dict] = {
    rule.id: {"message": rule.message, "level": rule.level, "domain": rule.domain}
    for rule in RULES
}
# 补充 FGR 相关规则
RULE_META_MAP.update({
    "FGR_CRITICAL_RISK": {"message": "FGR评估结果: 极高风险", "level": "RED", "domain": "fetal"},
    "FGR_HIGH_RISK": {"message": "FGR评估结果: 高风险", "level": "ORANGE", "domain": "fetal"},
    "FGR_MEDIUM_RISK": {"message": "FGR评估结果: 中风险", "level": "YELLOW", "domain": "fetal"},
    "EPDS_HIGH_RISK": {"message": "EPDS筛查高风险，建议心理干预", "level": "ORANGE", "domain": "mental"},
    "NURSE_AI_ALERT": {"message": "护士AI分析预警", "level": "ORANGE", "domain": "vital"},
})


def get_rule_message(rule_id: str) -> str | None:
    """根据规则ID获取正确的消息文本"""
    meta = RULE_META_MAP.get(rule_id)
    return meta["message"] if meta else None


def get_rule_level(rule_id: str) -> str | None:
    """根据规则ID获取正确的风险级别"""
    meta = RULE_META_MAP.get(rule_id)
    return meta["level"] if meta else None
