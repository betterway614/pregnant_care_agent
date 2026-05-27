"""业务逻辑修复单元测试

覆盖修复项：#1 session生命周期、#4 情绪否定词、#7 自杀关键词、#8 规则引擎括号
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4


# ==================== #1: enrich_alert_with_llm session 独立 ====================


class TestEnrichAlertSessionLifecycle:
    """验证 enrich_alert_with_llm 内部创建独立 session，不复用请求级 db"""

    @pytest.mark.asyncio
    async def test_creates_own_session_not_reuse_passed_db(self):
        """enrich_alert_with_llm 应创建自己的 SessionLocal，不使用外部传入的 db"""
        from app.services.alert_service import AlertService

        alert_id = uuid4()
        mock_session_local = MagicMock()
        mock_alert = MagicMock()
        mock_alert.id = alert_id
        mock_alert.details = {}
        mock_session_local.query.return_value.filter.return_value.first.return_value = mock_alert

        with patch("app.database.SessionLocal", return_value=mock_session_local), \
             patch("app.services.alert_analysis_service.alert_analysis_service.run_nurse_analysis",
                   new=AsyncMock(return_value=None)):
            await AlertService.enrich_alert_with_llm(alert_id, "P001")

        mock_session_local.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_closes_session_on_error(self):
        """即使 LLM 分析失败，session 也应被正确关闭"""
        from app.services.alert_service import AlertService

        mock_session_local = MagicMock()
        mock_session_local.query.return_value.filter.return_value.first.return_value = None

        with patch("app.database.SessionLocal", return_value=mock_session_local):
            await AlertService.enrich_alert_with_llm(uuid4(), "NONEXISTENT")

        mock_session_local.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_alert_id_and_pregnant_id_not_db_session(self):
        """函数签名应接受 alert_id + pregnant_id，不接受 db session"""
        import inspect
        from app.services.alert_service import AlertService

        sig = inspect.signature(AlertService.enrich_alert_with_llm)
        param_names = list(sig.parameters.keys())
        assert "db" not in param_names, "enrich_alert_with_llm 不应再接受 db 参数"
        assert "alert_id" in param_names
        assert "pregnant_id" in param_names


# ==================== #4: 情绪分析否定词过滤 ====================


class TestEmotionNegationFilter:
    """验证否定前缀能正确过滤正面词"""

    def setup_method(self):
        from app.core.nlu_engine import RuleBaseNLU
        self.nlu = RuleBaseNLU()

    def test_positive_without_negation(self):
        """无否定词时正常识别为 positive"""
        result = self.nlu._analyze_emotion("今天很开心")
        assert result["level"] == "positive"

    def test_negated_positive_bu_kai(self):
        """'不开心' 不应判为 positive"""
        result = self.nlu._analyze_emotion("不开心")
        assert result["level"] != "positive"

    def test_negated_positive_bu_hao(self):
        """'不好' 不应判为 positive"""
        result = self.nlu._analyze_emotion("不好")
        assert result["level"] != "positive"

    def test_negated_positive_mei_kai(self):
        """'没开心' 不应判为 positive"""
        result = self.nlu._analyze_emotion("没开心")
        assert result["level"] != "positive"

    def test_negated_positive_bu_gaoxing(self):
        """'不高兴' 不应判为 positive"""
        result = self.nlu._analyze_emotion("不高兴")
        assert result["level"] != "positive"

    def test_negated_positive_bu_cuobuo(self):
        """'不错' 中的 '不错' 应该是正面的（注意：不+错 = 正面含义）"""
        # "不错" 在中文里是正面意思，不是否定
        result = self.nlu._analyze_emotion("感觉不错")
        assert result["level"] == "positive"

    def test_mixed_sentiment_negation(self):
        """混合情绪：有焦虑词 + 被否定的正面词"""
        result = self.nlu._analyze_emotion("很焦虑，不好")
        # 焦虑词命中，即使有"好"也被否定，但焦虑本身应触发
        assert result["level"] in ("medium", "high")

    def test_anxiety_still_works(self):
        """焦虑词不受否定过滤影响"""
        result = self.nlu._analyze_emotion("很焦虑很紧张")
        assert result["level"] == "high"


# ==================== #7: NLU 自杀关键词扩展 ====================


class TestSuicideKeywordsExpansion:
    """验证自杀风险关键词覆盖范围"""

    def setup_method(self):
        from app.core.nlu_engine import RuleBaseNLU
        self.nlu = RuleBaseNLU()

    def test_original_keywords_still_work(self):
        """原始4个关键词仍有效"""
        for kw in ["自杀", "不想活", "想死", "活着没意思"]:
            result = self.nlu.parse(kw)
            assert result.intent == "SUICIDE_RISK", f"'{kw}' 应触发 SUICIDE_RISK"
            assert result.is_emergency is True

    def test_new_keyword_ge_wan(self):
        result = self.nlu.parse("我想割腕")
        assert result.intent == "SUICIDE_RISK"

    def test_new_keyword_tiao_lou(self):
        result = self.nlu.parse("想跳楼")
        assert result.intent == "SUICIDE_RISK"

    def test_new_keyword_jie_tuo(self):
        result = self.nlu.parse("想解脱")
        assert result.intent == "SUICIDE_RISK"

    def test_new_keyword_huo_bu_xiaqu(self):
        result = self.nlu.parse("活不下去了")
        assert result.intent == "SUICIDE_RISK"

    def test_new_keyword_xiang_jieshu(self):
        result = self.nlu.parse("想结束一切")
        assert result.intent == "SUICIDE_RISK"

    def test_new_keyword_meiyou_yiyi(self):
        result = self.nlu.parse("感觉没有意义")
        assert result.intent == "SUICIDE_RISK"

    def test_new_keyword_qingsheng(self):
        result = self.nlu.parse("想轻生")
        assert result.intent == "SUICIDE_RISK"

    def test_keyword_count_at_least_15(self):
        """SUICIDE_KEYWORDS 至少15个"""
        from app.core.nlu_engine import RuleBaseNLU
        assert len(RuleBaseNLU.SUICIDE_KEYWORDS) >= 15

    def test_normal_text_not_triggered(self):
        """普通文本不应触发自杀风险"""
        result = self.nlu.parse("今天天气不错")
        assert result.intent != "SUICIDE_RISK"
        assert result.is_emergency is False


# ==================== #8: 规则引擎括号支持 ====================


class TestRuleEngineParentheses:
    """验证 _safe_eval_condition 支持括号分组"""

    def test_simple_parentheses_or(self):
        from app.core.rule_engine import _safe_eval_condition
        vars_ = {"sbp": 145, "dbp": 80}
        # (sbp >= 140 or dbp >= 90) → True (sbp=145)
        assert _safe_eval_condition("(sbp >= 140 or dbp >= 90)", vars_) is True

    def test_parentheses_with_and(self):
        from app.core.rule_engine import _safe_eval_condition
        vars_ = {"sbp": 145, "dbp": 80, "gest_week": 35}
        # (sbp >= 140 or dbp >= 90) and gest_week >= 32 → True
        assert _safe_eval_condition("(sbp >= 140 or dbp >= 90) and gest_week >= 32", vars_) is True

    def test_parentheses_fails_when_inner_false(self):
        from app.core.rule_engine import _safe_eval_condition
        vars_ = {"sbp": 120, "dbp": 80}
        # (sbp >= 140 or dbp >= 90) → False
        assert _safe_eval_condition("(sbp >= 140 or dbp >= 90)", vars_) is False

    def test_nested_parentheses(self):
        from app.core.rule_engine import _safe_eval_condition
        vars_ = {"a": 1, "b": 2, "c": 3}
        # ((a >= 1 and b >= 2) or c >= 10) → True
        assert _safe_eval_condition("((a >= 1 and b >= 2) or c >= 10)", vars_) is True

    def test_parentheses_changes_result(self):
        """括号改变运算优先级"""
        from app.core.rule_engine import _safe_eval_condition
        vars_ = {"sbp": 145, "dbp": 80, "gest_week": 20}
        # 无括号: sbp >= 140 or dbp >= 90 and gest_week >= 32
        # and 优先级高于 or（在当前实现中从左到右，但括号版应更明确）
        # (sbp >= 140) or (dbp >= 90 and gest_week >= 32) → True (sbp=145)
        assert _safe_eval_condition("sbp >= 140 or (dbp >= 90 and gest_week >= 32)", vars_) is True

    def test_backward_compatible_no_parentheses(self):
        """无括号的原有规则仍正常工作"""
        from app.core.rule_engine import _safe_eval_condition
        vars_ = {"sbp": 145, "dbp": 95}
        assert _safe_eval_condition("sbp >= 140 or dbp >= 90", vars_) is True
        assert _safe_eval_condition("sbp >= 140 and dbp >= 90", vars_) is True
        assert _safe_eval_condition("sbp >= 200", vars_) is False

    def test_rule_evaluate_with_parentheses_expression(self):
        """Rule.evaluate 支持含括号的表达式"""
        from app.core.rule_engine import Rule
        rule = Rule("TEST", "vital", 1, "(sbp >= 140 or dbp >= 90) and gest_week >= 32", "RED", "test")
        context = {"sbp": 145, "dbp": 80, "gest_week": 35}
        assert rule.evaluate(context) is True

        context_fail = {"sbp": 120, "dbp": 80, "gest_week": 35}
        assert rule.evaluate(context_fail) is False


# ==================== 模型索引验证 ====================


class TestModelIndexes:
    """验证核心表索引已添加"""

    def test_alert_has_index(self):
        from app.models.models import Alert
        idx_names = [idx.name for idx in Alert.__table_args__]
        assert "idx_alert_pregnant_status" in idx_names

    def test_followup_record_has_index(self):
        from app.models.models import FollowUpRecord
        idx_names = [idx.name for idx in FollowUpRecord.__table_args__]
        assert "idx_followup_pregnant_status" in idx_names

    def test_medical_order_has_index(self):
        from app.models.models import MedicalOrder
        idx_names = [idx.name for idx in MedicalOrder.__table_args__]
        assert "idx_order_pregnant_status" in idx_names
