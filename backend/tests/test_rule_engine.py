"""规则引擎领域分组测试"""
import pytest
from app.core.rule_engine import RuleEngine, Rule, rule_engine


class TestDomainGrouping:
    """领域分组 + 优先级互斥"""

    def test_single_domain_returns_highest_priority_only(self):
        """同领域多条规则命中时，只返回优先级最高的"""
        engine = RuleEngine()
        context = {
            "sbp": 145, "dbp": 95, "weight": 65,
            "fetal_movement": 10, "fetal_movement_avg": 10,
            "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 4,
            "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
            "sleep_hours": 7, "gest_week": 20,
        }
        hits = engine.evaluate_all(context)
        vital_hits = [h for h in hits if h["domain"] == "vital"]
        assert len(vital_hits) == 1
        assert vital_hits[0]["level"] == "RED"
        assert vital_hits[0]["rule_id"] == "RULE_BP_HIGH"

    def test_domain_merges_same_priority_rules(self):
        """同领域同优先级规则合并 triggered_rules"""
        engine = RuleEngine()
        context = {
            "sbp": 132, "dbp": 86, "weight": 65,
            "fetal_movement": 10, "fetal_movement_avg": 10,
            "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 4,
            "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
            "sleep_hours": 7, "gest_week": 32,
        }
        hits = engine.evaluate_all(context)
        vital_hits = [h for h in hits if h["domain"] == "vital"]
        assert len(vital_hits) == 1
        assert vital_hits[0]["level"] == "ORANGE"
        assert "RULE_LATE_PREGNANCY_BP" in vital_hits[0]["triggered_rules"]
        assert "RULE_BP_HIGH_ORANGE" in vital_hits[0]["triggered_rules"]

    def test_multi_domain_returns_one_per_domain(self):
        """多领域同时触发时，每个领域最多一条"""
        engine = RuleEngine()
        context = {
            "sbp": 150, "dbp": 100, "weight": 65,
            "fetal_movement": 2, "fetal_movement_avg": 10,
            "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 1.2,
            "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
            "sleep_hours": 3, "gest_week": 25,
        }
        hits = engine.evaluate_all(context)
        domains = set(h["domain"] for h in hits)
        assert len(hits) == len(domains)  # 每个领域一条
        domain_map = {h["domain"]: h for h in hits}
        assert domain_map["vital"]["level"] == "RED"    # 血压150
        assert domain_map["fetal"]["level"] == "RED"    # 胎动2
        assert domain_map["mental"]["level"] == "ORANGE" # 情绪1.2触发EMOTION_HIGH

    def test_no_hits_returns_empty(self):
        """所有指标正常时不产生预警"""
        engine = RuleEngine()
        context = {
            "sbp": 120, "dbp": 80, "weight": 65,
            "fetal_movement": 10, "fetal_movement_avg": 10,
            "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 4,
            "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
            "sleep_hours": 8, "gest_week": 20,
        }
        hits = engine.evaluate_all(context)
        assert len(hits) == 0

    def test_each_rule_has_domain_and_priority(self):
        """所有规则都有 domain 和 priority 属性"""
        engine = RuleEngine()
        for rule in engine.rules:
            assert hasattr(rule, "domain"), f"{rule.id} missing domain"
            assert hasattr(rule, "priority"), f"{rule.id} missing priority"
            assert rule.domain in ("vital", "fetal", "mental")
            assert isinstance(rule.priority, int)

    def test_lower_priority_not_returned_when_higher_exists(self):
        """低优先级规则被高优先级覆盖"""
        engine = RuleEngine()
        context = {"sbp": 138, "dbp": 88, "gest_week": 20, "weight": 65,
                   "fetal_movement": 10, "fetal_movement_avg": 10,
                   "weight_gain_weekly": 0.5, "emotion_score_avg_7d": 4,
                   "blood_sugar_fasting": 4.5, "blood_sugar_postprandial": 6.0,
                   "sleep_hours": 7}
        hits = engine.evaluate_all(context)
        vital_hits = [h for h in hits if h["domain"] == "vital"]
        assert len(vital_hits) == 1
        # priority 2 (RULE_BP_HIGH_ORANGE) 覆盖 priority 1 (RULE_BP_LOW)
        assert vital_hits[0]["rule_id"] == "RULE_BP_HIGH_ORANGE"
        assert vital_hits[0]["level"] == "ORANGE"
