"""高危规则引擎 - CPU执行"""
import re
from typing import Callable
from datetime import datetime


class Rule:
    """规则定义"""
    def __init__(self, rule_id: str, expression: str, level: str,
                 message: str, action: str = "ALERT_NURSE"):
        self.id = rule_id
        self.expression = expression
        self.level = level
        self.message = message
        self.action = action

    def evaluate(self, context: dict) -> bool:
        """评估规则是否命中"""
        try:
            sbp = context.get("sbp", 0) or 0
            dbp = context.get("dbp", 0) or 0
            weight = context.get("weight", 0) or 0
            fetal_movement = context.get("fetal_movement", 0) or 0
            fetal_movement_avg = context.get("fetal_movement_avg", fetal_movement) or fetal_movement
            weight_gain_weekly = context.get("weight_gain_weekly", 0) or 0
            emotion_score = context.get("emotion_score_avg_7d", 0) or 0
            blood_sugar_fasting = context.get("blood_sugar_fasting", 0) or 0
            blood_sugar_postprandial = context.get("blood_sugar_postprandial", 0) or 0
            sleep_hours = context.get("sleep_hours", 8) or 8
            gest_week = context.get("gest_week", 0) or 0

            return bool(eval(self.expression, {
                "sbp": sbp, "dbp": dbp,
                "weight": weight,
                "fetal_movement": fetal_movement,
                "fetal_movement_avg": fetal_movement_avg,
                "weight_gain_weekly": weight_gain_weekly,
                "emotion_score": emotion_score,
                "emotion_score_avg_7d": emotion_score,
                "blood_sugar_fasting": blood_sugar_fasting,
                "blood_sugar_postprandial": blood_sugar_postprandial,
                "sleep_hours": sleep_hours,
                "gest_week": gest_week,
            }))
        except Exception:
            return False


# 规则定义 - 从 5 条扩展到 15+ 条
RULES = [
    # === 血压规则 ===
    Rule("RULE_BP_HIGH", "sbp >= 140 or dbp >= 90", "RED",
         "血压异常升高（≥140/90mmHg）", "ALERT_NURSE_AND_DOCTOR"),
    Rule("RULE_BP_HIGH_ORANGE", "sbp >= 135 or dbp >= 85", "ORANGE",
         "血压偏高（≥135/85mmHg），需要关注", "ALERT_NURSE"),
    Rule("RULE_BP_LOW", "sbp < 90 or dbp < 60", "YELLOW",
         "血压偏低，需关注", "NOTE_NURSE"),

    # === 胎动规则 ===
    Rule("RULE_FETAL_DROP", "fetal_movement < fetal_movement_avg * 0.5", "RED",
         "胎动显著减少（低于平均50%）", "ALERT_NURSE_AND_PATIENT"),
    Rule("RULE_FETAL_VERY_LOW", "fetal_movement < 3", "RED",
         "胎动极少（<3次/小时），请立即就医", "ALERT_NURSE_AND_PATIENT"),

    # === 体重规则 ===
    Rule("RULE_WEIGHT_GAIN_FAST", "weight_gain_weekly > 2.0", "ORANGE",
         "体重周增长过快（>2kg/周）", "ALERT_NURSE"),
    Rule("RULE_WEIGHT_GAIN_SLOW", "weight_gain_weekly < 0.1 and gest_week > 12", "YELLOW",
         "体重增长过慢，需关注营养摄入", "NOTE_NURSE"),

    # === 血糖规则（GDM管理）===
    Rule("RULE_BS_FASTING_HIGH", "blood_sugar_fasting > 5.3", "ORANGE",
         "空腹血糖偏高（>5.3mmol/L），建议复查", "ALERT_NURSE"),
    Rule("RULE_BS_POSTPRANDIAL_HIGH", "blood_sugar_postprandial > 7.0", "RED",
         "餐后血糖异常（>7.0mmol/L）", "ALERT_NURSE_AND_DOCTOR"),

    # === 情绪规则 ===
    Rule("RULE_EMOTION_HIGH", "emotion_score_avg_7d >= 7", "YELLOW",
         "近7日情绪评分偏高，需关注心理状态", "NOTE_NURSE"),
    Rule("RULE_EMOTION_CRITICAL", "emotion_score_avg_7d >= 9", "ORANGE",
         "情绪评分严重偏高，建议心理干预", "ALERT_NURSE"),

    # === 睡眠规则 ===
    Rule("RULE_SLEEP_SHORT", "sleep_hours < 5", "YELLOW",
         "睡眠不足5小时，建议改善睡眠", "NOTE_NURSE"),

    # === 孕周相关规则 ===
    Rule("RULE_LATE_PREGNANCY_BP", "sbp >= 130 and gest_week >= 32", "ORANGE",
         "孕晚期血压偏高，子痫前期风险", "ALERT_NURSE_AND_DOCTOR"),
]


class RuleEngine:
    """规则引擎"""

    def __init__(self):
        self.rules = RULES

    def evaluate_all(self, context: dict) -> list[dict]:
        """评估全部规则，返回命中规则列表"""
        hits = []
        for rule in self.rules:
            if rule.evaluate(context):
                hits.append({
                    "rule_id": rule.id,
                    "level": rule.level,
                    "message": rule.message,
                    "action": rule.action,
                })
        return hits

    def evaluate_fgr_risk(self, risk_level: str) -> list[dict]:
        """FGR风险等级触发规则"""
        alerts = []
        if risk_level in ("high", "critical"):
            alerts.append({
                "rule_id": "FGR_HIGH_RISK",
                "level": "RED" if risk_level == "critical" else "ORANGE",
                "message": f"FGR评估结果: {risk_level}风险",
                "action": "ALERT_DOCTOR",
            })
        elif risk_level == "medium":
            alerts.append({
                "rule_id": "FGR_MEDIUM_RISK",
                "level": "YELLOW",
                "message": "FGR评估结果: 中风险",
                "action": "ALERT_NURSE",
            })
        return alerts


# 全局单例
rule_engine = RuleEngine()
