"""测试 OrderService - 医嘱模板服务 + 文档生成"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ==================== 医嘱模板推荐 ====================


class TestOrderRecommendation:
    """测试风险匹配模板推荐"""

    def test_fgr_high_before_34w(self):
        """FGR高风险 + 孕周<34w 应推荐收治建议"""
        from app.services.order_service import order_service

        result = order_service.get_recommendation("high", 30, ["FGR"])
        assert result is not None
        assert "收治入院" in result["content"] or "建议" in result["content"]
        assert "地塞米松" in result["content"]

    def test_fgr_high_after_34w(self):
        """FGR高风险 + 孕周>=34w 应推荐分娩评估建议"""
        from app.services.order_service import order_service

        result = order_service.get_recommendation("high", 36, ["FGR"])
        assert result is not None
        assert "分娩" in result["content"] or "剖宫产" in result["content"]

    def test_fgr_medium(self):
        """FGR中风险应推荐门诊随访建议"""
        from app.services.order_service import order_service

        result = order_service.get_recommendation("medium", 28, ["FGR"])
        assert result is not None
        assert "门诊" in result["content"]

    def test_hypertension_mild(self):
        """轻度高血压应推荐门诊降压建议"""
        from app.services.order_service import order_service

        result = order_service.get_recommendation("medium", 24, ["高血压"])
        assert result is not None
        assert "降压" in result["content"] or "血压" in result["content"]

    def test_gestational_diabetes(self):
        """GDM应推荐血糖监测建议"""
        from app.services.order_service import order_service

        result = order_service.get_recommendation("medium", 26, ["GDM"])
        assert result is not None
        assert "血糖" in result["content"]

    def test_no_match_returns_none(self):
        """无风险标签时应返回None"""
        from app.services.order_service import order_service

        result = order_service.get_recommendation("low", 20, [])
        assert result is None

    def test_get_all_templates(self):
        """获取所有模板应返回字典"""
        from app.services.order_service import order_service

        templates = order_service.get_all_templates()
        assert isinstance(templates, dict)
        assert len(templates) > 0


# ==================== 医嘱文档生成 ====================


class TestGenerateOrderDocument:
    """测试 generate_order_document() 方法"""

    def test_generates_snapshot_with_all_fields(self):
        """验证快照包含所有必要字段"""
        from app.services.order_service import order_service

        snapshot, text = order_service.generate_order_document(
            patient_name="测试孕妇",
            gest_week="24+3",
            order_content="建议低盐饮食，每日监测血压",
            order_type="standard",
            source="AI_RECOMMENDED",
            doctor_name="张医生",
        )

        assert snapshot["patient_name"] == "测试孕妇"
        assert snapshot["gestational_week"] == "24+3"
        assert snapshot["order_content"] == "建议低盐饮食，每日监测血压"
        assert snapshot["order_type"] == "standard"
        assert snapshot["source"] == "AI_RECOMMENDED"
        assert snapshot["doctor_name"] == "张医生"
        assert "generated_at" in snapshot

    def test_text_contains_patient_info(self):
        """验证纯文本文档包含患者信息"""
        from app.services.order_service import order_service

        _, text = order_service.generate_order_document(
            patient_name="测试孕妇",
            gest_week="30+0",
            order_content="建议每2周产检一次",
            order_type="standard",
            source="DOCTOR_WRITTEN",
            doctor_name="",
        )

        assert "测试孕妇" in text
        assert "30+0" in text
        assert "建议每2周产检一次" in text
        assert "医 嘱 单" in text

    def test_text_contains_platform_branding(self):
        """验证文档包含平台标识"""
        from app.services.order_service import order_service

        _, text = order_service.generate_order_document(
            patient_name="张三",
            gest_week="20+0",
            order_content="按时产检",
            order_type="standard",
            source="AI_RECOMMENDED",
            doctor_name="",
        )

        assert "AI-Care" in text

    def test_text_contains_red_warning(self):
        """验证文档包含红色警告提醒"""
        from app.services.order_service import order_service

        _, text = order_service.generate_order_document(
            patient_name="张三",
            gest_week="20+0",
            order_content="按时产检",
            order_type="standard",
            source="AI_RECOMMENDED",
            doctor_name="",
        )

        assert "医生审核修改" in text
        assert "手写签名确认" in text

    def test_text_has_signature_placeholder(self):
        """验证文档包含签名占位符"""
        from app.services.order_service import order_service

        _, text = order_service.generate_order_document(
            patient_name="张三",
            gest_week="20+0",
            order_content="按时产检",
            order_type="standard",
            source="AI_RECOMMENDED",
            doctor_name="",
        )

        assert "医生签名" in text

    def test_text_fills_doctor_name_when_provided(self):
        """验证提供医生姓名时文档显示医生姓名"""
        from app.services.order_service import order_service

        _, text = order_service.generate_order_document(
            patient_name="张三",
            gest_week="20+0",
            order_content="按时产检",
            order_type="standard",
            source="AI_RECOMMENDED",
            doctor_name="李医生",
        )

        assert "李医生" in text

    def test_source_label_mapping(self):
        """验证来源标签正确映射"""
        from app.services.order_service import order_service

        # AI_RECOMMENDED
        _, text_ai = order_service.generate_order_document(
            patient_name="张三", gest_week="20+0", order_content="test",
            order_type="standard", source="AI_RECOMMENDED", doctor_name="",
        )
        assert "AI辅助生成" in text_ai

        # DOCTOR_WRITTEN
        _, text_doc = order_service.generate_order_document(
            patient_name="张三", gest_week="20+0", order_content="test",
            order_type="standard", source="DOCTOR_WRITTEN", doctor_name="",
        )
        assert "医生手写" in text_doc


# ==================== 医嘱模板措辞检查 ====================


class TestOrderTemplateWording:
    """验证所有医嘱模板使用建议性措辞（非诊断性）"""

    DIAGNOSTIC_PATTERNS = ["收治入院", "予", "启动", "立即就诊"]

    def test_fgr_templates_use_suggestive_language(self):
        """FGR模板应使用'建议'等建议性措辞"""
        from app.services.order_service import ORDER_TEMPLATES

        for key in ["fgr_high_before_34", "fgr_high_after_34", "fgr_medium"]:
            content = ORDER_TEMPLATES[key]["content"]
            assert "建议" in content, f"{key} 缺少'建议'关键词"
            assert "具体方案需经主治医生评估" in content or "以上为医疗建议" in content, \
                f"{key} 缺少免责声明"

    def test_hypertension_templates_use_suggestive_language(self):
        """高血压模板应使用建议性措辞"""
        from app.services.order_service import ORDER_TEMPLATES

        for key in ["hypertension_severe", "hypertension_mild"]:
            content = ORDER_TEMPLATES[key]["content"]
            assert "建议" in content, f"{key} 缺少'建议'关键词"

    def test_all_templates_have_disclaimer(self):
        """所有模板应包含免责声明"""
        from app.services.order_service import ORDER_TEMPLATES

        for key, tmpl in ORDER_TEMPLATES.items():
            content = tmpl["content"]
            has_disclaimer = (
                "具体方案需经主治医生评估" in content
                or "具体用药方案需经" in content
                or "以上为医疗建议" in content
                or "具体用药方案需医生" in content
            )
            assert has_disclaimer, f"{key} 缺少免责声明: {content[:50]}"
