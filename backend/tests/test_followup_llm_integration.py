"""护士端随访 LLM 深度集成 — 单元测试

覆盖改进1-4的核心逻辑：
- 改进1: 结构化随访分析报告 (_fallback_analysis_report, FollowUpAnalysisReport)
- 改进2: AI审核辅助 (FollowUpAiReviewResponse, create_followup_review_agent)
- 改进3: 批量排期推荐 (tool_recommend_followup_schedule)
- 改进4: 个性化健康教育 (generate_health_education_with_llm)
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


# ==================== 改进1: 结构化随访分析报告 ====================

class TestFollowUpAnalysisReport:
    """测试 FollowUpAnalysisReport Schema 验证"""

    def test_schema_valid(self):
        from app.schemas import FollowUpAnalysisReport
        report = FollowUpAnalysisReport(
            warm_summary="感谢配合，一切正常~",
            abnormal_indicators=[],
            trend_analysis="各项指标稳定",
            personalized_advice="继续保持良好作息",
            nurse_action_suggestion="确认通过",
        )
        assert report.warm_summary == "感谢配合，一切正常~"
        assert report.abnormal_indicators == []
        assert report.nurse_action_suggestion == "确认通过"

    def test_schema_with_abnormal_indicators(self):
        from app.schemas import FollowUpAnalysisReport
        report = FollowUpAnalysisReport(
            warm_summary="有指标需要关注",
            abnormal_indicators=["血压偏高（150/95mmHg）", "空腹血糖偏高（6.1mmol/L）"],
            trend_analysis="血压呈上升趋势",
            personalized_advice="建议低盐饮食",
            nurse_action_suggestion="需进一步沟通",
        )
        assert len(report.abnormal_indicators) == 2
        assert "血压偏高" in report.abnormal_indicators[0]

    def test_schema_defaults(self):
        from app.schemas import FollowUpAnalysisReport
        report = FollowUpAnalysisReport(warm_summary="test")
        assert report.abnormal_indicators == []
        assert report.trend_analysis == ""
        assert report.personalized_advice == ""
        assert report.nurse_action_suggestion == ""


class TestFallbackAnalysisReport:
    """测试模板兜底的随访分析报告"""

    def test_normal_bp_returns_pass(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="小明",
            gest_week="28+3",
            answers={"bp": "120/80", "weight": "65"},
            risk_tags=[],
        )
        assert result["warm_summary"]
        assert "小明" in result["warm_summary"]
        assert result["abnormal_indicators"] == []
        assert result["nurse_action_suggestion"] == "确认通过"

    def test_high_bp_detected(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="小红",
            gest_week="32+0",
            answers={"bp": "150/95", "weight": "70"},
            risk_tags=["高血压"],
        )
        assert len(result["abnormal_indicators"]) > 0
        assert "血压偏高" in result["abnormal_indicators"][0]
        assert result["nurse_action_suggestion"] == "需进一步沟通"

    def test_borderline_bp_detected(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="小华",
            gest_week="30+0",
            answers={"bp": "136/86"},
            risk_tags=[],
        )
        assert len(result["abnormal_indicators"]) > 0
        assert "临界" in result["abnormal_indicators"][0]

    def test_high_fasting_glucose_detected(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="小丽",
            gest_week="26+0",
            answers={"blood_sugar_fasting": "6.2"},
            risk_tags=["GDM"],
        )
        assert any("空腹血糖" in a for a in result["abnormal_indicators"])

    def test_low_fetal_movement_detected(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="小芳",
            gest_week="34+0",
            answers={"fetal_movement": "2"},
            risk_tags=[],
        )
        assert any("胎动" in a for a in result["abnormal_indicators"])

    def test_multiple_abnormal_indicators(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="小敏",
            gest_week="36+0",
            answers={"bp": "155/100", "blood_sugar_fasting": "5.8", "fetal_movement": "1"},
            risk_tags=["高血压", "GDM"],
        )
        assert len(result["abnormal_indicators"]) >= 2
        assert result["nurse_action_suggestion"] == "需进一步沟通"

    def test_no_answers(self):
        from app.routers.followup import _fallback_analysis_report
        result = _fallback_analysis_report(
            patient_name="小新",
            gest_week="20+0",
            answers={},
            risk_tags=[],
        )
        assert result["abnormal_indicators"] == []
        assert result["nurse_action_suggestion"] == "确认通过"


class TestFollowUpAnalysisAgent:
    """测试随访分析 Agent 工厂"""

    def test_followup_analysis_agent_has_output_schema(self):
        from app.core.agno_medical_agents import create_followup_analysis_agent, FollowUpAnalysisOutput

        mock_model = MagicMock()
        mock_model.__class__.__name__ = "MockModel"
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_followup_analysis_agent()
                assert agent.name == "小安-随访分析"
                assert agent.output_schema == FollowUpAnalysisOutput

    def test_followup_analysis_output_schema_fields(self):
        from app.core.agno_medical_agents import FollowUpAnalysisOutput
        fields = FollowUpAnalysisOutput.model_fields
        assert "warm_summary" in fields
        assert "abnormal_indicators" in fields
        assert "trend_analysis" in fields
        assert "personalized_advice" in fields
        assert "nurse_action_suggestion" in fields


# ==================== 改进2: AI 审核辅助 ====================

class TestFollowUpAiReview:
    """测试 AI 审核辅助"""

    def test_review_schema_valid(self):
        from app.schemas import FollowUpAiReviewResponse
        response = FollowUpAiReviewResponse(
            summary="孕妇小明孕28周随访，各项指标基本正常",
            abnormal_flags=[],
            action_needed=False,
            recommendation="确认通过",
            detail_analysis="血压120/80mmHg，体重增长合理",
        )
        assert response.action_needed is False
        assert response.recommendation == "确认通过"

    def test_review_schema_with_abnormal(self):
        from app.schemas import FollowUpAiReviewResponse
        response = FollowUpAiReviewResponse(
            summary="发现异常指标",
            abnormal_flags=["血压偏高150/95", "胎动偏少"],
            action_needed=True,
            recommendation="紧急上报",
            detail_analysis="多项指标异常，需立即关注",
        )
        assert response.action_needed is True
        assert len(response.abnormal_flags) == 2

    def test_review_agent_has_output_schema(self):
        from app.core.agno_medical_agents import create_followup_review_agent, FollowUpAiReviewOutput

        mock_model = MagicMock()
        mock_model.__class__.__name__ = "MockModel"
        with patch("app.core.agno_medical_agents.get_agno_model", return_value=mock_model):
            with patch("agno.agent._init.get_model", return_value=mock_model):
                agent = create_followup_review_agent()
                assert agent.name == "小护-审核辅助"
                assert agent.output_schema == FollowUpAiReviewOutput

    def test_review_agent_output_schema_fields(self):
        from app.core.agno_medical_agents import FollowUpAiReviewOutput
        fields = FollowUpAiReviewOutput.model_fields
        assert "summary" in fields
        assert "abnormal_flags" in fields
        assert "action_needed" in fields
        assert "recommendation" in fields
        assert "detail_analysis" in fields


# ==================== 改进3: 批量排期推荐 ====================

class TestBatchRecommendations:
    """测试批量排期推荐逻辑"""

    def test_tool_recommend_returns_recommendations(self):
        """验证 tool_recommend_followup_schedule 返回正确的推荐结构"""
        from app.routers.nurse_ai import tool_recommend_followup_schedule

        db = MagicMock()
        mock_pregnant = MagicMock()
        mock_pregnant.pregnant_id = "P001"
        mock_pregnant.display_name = "测试孕妇"
        mock_pregnant.gestational_age_days = 210  # 30周
        mock_pregnant.risk_tags = []
        db.query.return_value.filter.return_value.first.return_value = mock_pregnant
        db.query.return_value.filter.return_value.all.return_value = []
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        # Mock func.count
        with patch("app.routers.nurse_ai.func") as mock_func:
            mock_func.count.return_value = MagicMock()
            db.query.return_value.filter.return_value.scalar.return_value = 0
            result = tool_recommend_followup_schedule(db, "P001")

        assert "pregnant_id" in result
        assert result["pregnant_id"] == "P001"
        assert "recommendations" in result
        assert "current_gestational_week" in result

    def test_tool_recommend_high_risk_immediate(self):
        """验证高危孕妇有立即随访推荐"""
        from app.routers.nurse_ai import tool_recommend_followup_schedule

        db = MagicMock()
        mock_pregnant = MagicMock()
        mock_pregnant.pregnant_id = "P002"
        mock_pregnant.display_name = "高危孕妇"
        mock_pregnant.gestational_age_days = 252  # 36周
        mock_pregnant.risk_tags = ["FGR高危"]

        # Mock RED 级别预警
        mock_alert = MagicMock()
        mock_alert.level = "RED"
        mock_alert.message = "胎动异常减少"
        mock_alert.status = "PENDING"

        db.query.return_value.filter.return_value.first.return_value = mock_pregnant
        db.query.return_value.filter.return_value.all.return_value = [mock_alert]
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with patch("app.routers.nurse_ai.func") as mock_func:
            mock_func.count.return_value = MagicMock()
            db.query.return_value.filter.return_value.scalar.return_value = 0
            result = tool_recommend_followup_schedule(db, "P002")

        immediate_recs = [r for r in result["recommendations"] if r["recommended_date"] == "immediate"]
        assert len(immediate_recs) > 0
        assert immediate_recs[0]["priority"] == "high"


# ==================== 改进4: 个性化健康教育 ====================

class TestPersonalizedHealthEducation:
    """测试 LLM 个性化健康教育生成"""

    @pytest.mark.asyncio
    async def test_llm_health_education_uses_llm_when_enabled(self):
        """验证 LLM 启用时调用 LLM 生成个性化教育"""
        from app.services.followup_service import FollowUpService

        service = FollowUpService()

        mock_response = '["建议少量多餐缓解孕吐", "保证充足休息和叶酸补充", "避免剧烈运动"]'
        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=mock_response)

        with patch("app.config.settings") as mock_settings:
            mock_settings.agno_enabled = True
            with patch("app.core.get_llm_client", return_value=mock_client):
                result = await service.generate_health_education_with_llm(
                    gest_week=10,
                    risk_tags=[],
                    answers={"feeling": "有点恶心", "nausea": "早上比较严重"},
                )

        assert len(result) >= 2
        assert any("孕吐" in item or "少量多餐" in item for item in result)

    @pytest.mark.asyncio
    async def test_llm_health_education_falls_back_on_failure(self):
        """验证 LLM 失败时回退到模板"""
        from app.services.followup_service import FollowUpService

        service = FollowUpService()

        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(side_effect=Exception("LLM connection error"))

        with patch("app.config.settings") as mock_settings:
            mock_settings.agno_enabled = True
            with patch("app.core.get_llm_client", return_value=mock_client):
                result = await service.generate_health_education_with_llm(
                    gest_week=28,
                    risk_tags=["GDM"],
                    answers={"blood_sugar_fasting": "5.8"},
                )

        # 回退到模板+关键词匹配
        assert len(result) >= 2
        assert any("血糖" in item or "GDM" in item for item in result)

    @pytest.mark.asyncio
    async def test_llm_health_education_adds_sleep_tips(self):
        """验证回答中提到失眠时添加针对性建议"""
        from app.services.followup_service import FollowUpService

        service = FollowUpService()

        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=None)  # LLM 返回空

        with patch("app.config.settings") as mock_settings:
            mock_settings.agno_enabled = True
            with patch("app.core.get_llm_client", return_value=mock_client):
                result = await service.generate_health_education_with_llm(
                    gest_week=28,
                    risk_tags=[],
                    answers={"feeling": "最近经常失眠睡不好"},
                )

        assert any("睡眠" in item for item in result)

    @pytest.mark.asyncio
    async def test_llm_health_education_adds_stress_tips(self):
        """验证回答中提到压力时添加心理健康建议"""
        from app.services.followup_service import FollowUpService

        service = FollowUpService()

        mock_client = AsyncMock()
        mock_client.chat = AsyncMock(return_value=None)

        with patch("app.config.settings") as mock_settings:
            mock_settings.agno_enabled = True
            with patch("app.core.get_llm_client", return_value=mock_client):
                result = await service.generate_health_education_with_llm(
                    gest_week=30,
                    risk_tags=[],
                    answers={"stress": "工作压力很大"},
                )

        assert any("心理" in item for item in result)

    def test_template_health_education_by_week(self):
        """验证模板健康教育按孕周正确分段"""
        from app.services.followup_service import followup_service

        early = followup_service.generate_health_education(10, [])
        assert any("叶酸" in item for item in early)

        mid = followup_service.generate_health_education(20, [])
        assert any("胎动" in item for item in mid)

        late = followup_service.generate_health_education(38, [])
        assert any("临产" in item for item in late)

    def test_template_health_education_by_risk(self):
        """验证模板健康教育按风险标签正确补充"""
        from app.services.followup_service import followup_service

        gdm = followup_service.generate_health_education(28, ["GDM"])
        assert any("血糖" in item for item in gdm)

        htn = followup_service.generate_health_education(28, ["高血压"])
        assert any("血压" in item for item in htn)


# ==================== 改进8: 归档文档生成 ====================

class TestRecordDocument:
    """测试归档文档生成（record_snapshot + record_text）"""

    def test_generate_record_document_basic(self):
        from app.services.followup_service import followup_service

        record = {
            "status": "confirmed",
            "classification": "normal",
            "chief_complaint": "无",
            "self_reported_data": {"weight": "65.6", "fetal_movement": "8"},
            "obstetric_exam": {"fundal_height_cm": 25.0, "fetal_heart_rate_bpm": 140},
            "lab_results": {"hemoglobin_g_L": 120.0, "urine_protein": "阴性"},
            "summary": "孕28周随访，各项指标正常",
            "guidance_tags": [{"tag": "营养", "content": "均衡饮食"}],
            "next_followup_date": "2026-06-15",
            "reviewed_by": "nurse_WANG",
            "reviewed_at": "2026-05-20",
            "review_comment": "确认通过",
            "ai_snapshot": {},
        }

        snapshot, text = followup_service.generate_record_document(
            patient_name="小明", gest_week="28+3",
            follow_up_date="2026-05-20", record=record,
        )

        # 快照检查
        assert snapshot["patient_name"] == "小明"
        assert snapshot["gestational_week"] == "28+3"
        assert snapshot["classification"] == "normal"
        assert "weight" in snapshot["self_reported_data"]

        # 纯文本检查
        assert "小明" in text
        assert "28+3" in text
        assert "S 主观数据" in text
        assert "O 客观检查" in text
        assert "A 评估" in text
        assert "P 计划" in text
        assert "审核信息" in text
        assert "随访护士签名" in text
        assert "[营养] 均衡饮食" in text
        assert "宫高" in text

    def test_generate_record_document_abnormal(self):
        from app.services.followup_service import followup_service

        record = {
            "status": "confirmed",
            "classification": "critical",
            "self_reported_data": {"bp": "155/100"},
            "obstetric_exam": {"blood_pressure": "155/100"},
            "lab_results": {},
            "summary": "血压异常",
            "guidance_tags": [{"tag": "生活", "content": "低盐饮食"}],
            "reviewed_by": "nurse_ZHANG",
            "review_comment": "已复核，建议转诊",
            "referral": {"has_referral": True, "reason": "血压持续偏高", "institution": "妇幼保健院", "department": "高危门诊"},
        }

        snapshot, text = followup_service.generate_record_document(
            patient_name="小红", gest_week="32+0",
            follow_up_date="2026-05-20", record=record,
        )

        assert snapshot["classification"] == "critical"
        assert "高危" in text
        assert "转诊" in text
        assert "妇幼保健院" in text
        assert "已复核" in text

    def test_generate_record_document_empty(self):
        from app.services.followup_service import followup_service

        record = {"status": "draft", "classification": "normal", "self_reported_data": {}, "obstetric_exam": {}}
        snapshot, text = followup_service.generate_record_document("测试", "20+0", "2026-01-01", record)

        assert "S 主观数据" in text
        assert "O 客观检查" in text
        assert "随访护士签名" in text

    def test_record_text_has_signature_line(self):
        """验证归档文本包含签名栏"""
        from app.services.followup_service import followup_service

        _, text = followup_service.generate_record_document(
            "测试", "20+0", "2026-01-01",
            {"status": "confirmed", "self_reported_data": {}, "obstetric_exam": {}, "lab_results": {}},
        )
        assert "随访护士签名：__________________" in text
        # 不应包含孕妇签名
        assert "孕妇签名" not in text


# ==================== 改进8: Pydantic None转换器 ====================

class TestSchemaNoneConversions:
    """测试 Pydantic Schema 的 None→默认值 转换器"""

    def test_none_dict_fields_convert_to_empty_dict(self):
        from app.schemas import FollowUpRecordResponse
        r = FollowUpRecordResponse(
            id="00000000-0000-0000-0000-000000000001",
            pregnant_id="P001",
            self_reported_data=None,
            obstetric_exam=None,
            lab_results=None,
            ai_snapshot=None,
            record_snapshot=None,
            signature_data=None,
        )
        assert r.self_reported_data == {}
        assert r.obstetric_exam == {}
        assert r.lab_results == {}
        assert r.ai_snapshot == {}
        assert r.record_snapshot == {}
        assert r.signature_data == {}

    def test_none_list_fields_convert_to_empty_list(self):
        from app.schemas import FollowUpRecordResponse
        r = FollowUpRecordResponse(
            id="00000000-0000-0000-0000-000000000001",
            pregnant_id="P001",
            health_education=None,
            guidance_tags=None,
        )
        assert r.health_education == []
        assert r.guidance_tags == []

    def test_valid_values_pass_through(self):
        from app.schemas import FollowUpRecordResponse
        r = FollowUpRecordResponse(
            id="00000000-0000-0000-0000-000000000001",
            pregnant_id="P001",
            self_reported_data={"weight": "65"},
            health_education=["指导1"],
            guidance_tags=[{"tag": "营养", "content": "test"}],
        )
        assert r.self_reported_data == {"weight": "65"}
        assert r.health_education == ["指导1"]
        assert len(r.guidance_tags) == 1

    def test_history_record_none_conversions(self):
        from app.schemas import FollowUpHistoryRecord
        r = FollowUpHistoryRecord(
            id="test",
            self_reported_data=None,
            obstetric_exam=None,
            lab_results=None,
            health_education=None,
            guidance_tags=None,
        )
        assert r.self_reported_data == {}
        assert r.obstetric_exam == {}
        assert r.health_education == []
        assert r.guidance_tags == []


# ==================== 改进8: 归档接口集成测试 ====================

class TestArchiveEndpoints:
    """测试归档相关 API 端点"""

    def test_sign_record_schema(self):
        """验证签名请求 Schema"""
        from app.schemas import FollowUpSignatureRequest
        req = FollowUpSignatureRequest(
            signature_image="data:image/png;base64,iVBOR...",
            signer_name="护士A",
        )
        assert req.signature_image.startswith("data:image")
        assert req.signer_name == "护士A"

    def test_followup_confirm_schema(self):
        """验证审核请求 Schema 支持归档参数"""
        from app.schemas import FollowUpConfirm
        c = FollowUpConfirm(
            status="confirmed",
            reviewer_id="nurse_001",
            review_comment="确认通过",
            ai_snapshot={"warm_summary": "正常"},
        )
        assert c.reviewer_id == "nurse_001"
        assert c.review_comment == "确认通过"
        assert c.ai_snapshot["warm_summary"] == "正常"

    def test_followup_record_response_has_archive_fields(self):
        """验证响应 Schema 包含所有归档字段"""
        from app.schemas import FollowUpRecordResponse
        fields = set(FollowUpRecordResponse.model_fields.keys())
        assert "record_snapshot" in fields
        assert "record_text" in fields
        assert "signature_data" in fields
        assert "obstetric_exam" in fields
        assert "lab_results" in fields
        assert "classification" in fields
        assert "guidance_tags" in fields
        assert "reviewed_by" in fields

    def test_document_endpoint_returns_correct_structure(self):
        """验证 /document 端点返回正确结构（mock）"""
        from app.routers.followup import get_record_document
        from unittest.mock import MagicMock, patch
        from uuid import uuid4

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.pregnant_id = "P001"
        mock_record.record_snapshot = {"patient_name": "小明", "classification": "normal"}
        mock_record.record_text = "随访记录单\n孕妇：小明"
        mock_record.signature_data = {"image": "base64...", "signer": "护士"}

        mock_pregnant = MagicMock()
        mock_pregnant.display_name = "小明"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.side_effect = [mock_record, mock_pregnant]

        with patch("app.routers.followup.SessionLocal", return_value=mock_db):
            result = get_record_document(str(mock_record.id))

        assert result["patient_name"] == "小明"
        assert result["has_document"] is True
        assert "snapshot" in result
        assert "text" in result
        assert "signature" in result
