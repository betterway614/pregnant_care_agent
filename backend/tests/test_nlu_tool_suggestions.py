"""测试 NLU 工具推荐功能"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.nlu_engine import nlu_engine


def test_weight_entity_suggests_save_and_trends():
    """体重数据 → 推荐 save + trends"""
    result = nlu_engine.parse("体重65kg")
    assert "agno_save_health_data" in result.suggested_tools
    assert "agno_analyze_health_trends" in result.suggested_tools


def test_bp_entity_suggests_save_and_trends():
    """血压数据 → 推荐 save + trends"""
    result = nlu_engine.parse("血压130/85")
    assert "agno_save_health_data" in result.suggested_tools
    assert "agno_analyze_health_trends" in result.suggested_tools


def test_bp_with_assess_suggests_rules():
    """血压数据 + 评估关键词 → 推荐 save + rules"""
    result = nlu_engine.parse("血压130/85，评估一下是否正常")
    assert "agno_save_health_data" in result.suggested_tools
    assert "agno_evaluate_vital_rules" in result.suggested_tools


def test_fetal_movement_entity_suggests_save():
    """胎动数据 → 推荐 save"""
    result = nlu_engine.parse("胎动8次")
    assert "agno_save_health_data" in result.suggested_tools


def test_trend_keyword_suggests_trends():
    """含趋势关键词 → 推荐 trends"""
    result = nlu_engine.parse("看看血压趋势")
    assert "agno_analyze_health_trends" in result.suggested_tools


def test_assess_keyword_suggests_rules():
    """含评估关键词 → 推荐 rules"""
    result = nlu_engine.parse("评估一下是否正常")
    assert "agno_evaluate_vital_rules" in result.suggested_tools


def test_epds_keyword_suggests_epds():
    """含心理评估关键词 → 推荐 EPDS"""
    result = nlu_engine.parse("做一下心理评估")
    assert "agno_get_epds_result" in result.suggested_tools


def test_knowledge_query_suggests_search():
    """知识查询 → 推荐 search_knowledge"""
    result = nlu_engine.parse("什么是妊娠期糖尿病")
    assert "agno_search_knowledge" in result.suggested_tools


def test_greeting_suggests_no_tools():
    """问候语 → 无推荐工具"""
    result = nlu_engine.parse("你好")
    assert result.suggested_tools == []


def test_no_duplicate_tools():
    """推荐工具无重复"""
    result = nlu_engine.parse("体重65kg，看看体重趋势")
    assert len(result.suggested_tools) == len(set(result.suggested_tools))


def test_suggested_tools_in_nlu_context():
    """验证 suggested_tools 会通过 _nlu_context 传递"""
    from app.core.agno_tools import _nlu_context

    session_id = "test-tools-ctx"
    result = nlu_engine.parse("血压130/85，帮我评估一下")
    nlu_dict = {
        "intent": result.intent,
        "entities": result.entities,
        "suggested_tools": result.suggested_tools,
    }
    _nlu_context[session_id] = nlu_dict

    assert "agno_save_health_data" in _nlu_context[session_id]["suggested_tools"]
    assert "agno_evaluate_vital_rules" in _nlu_context[session_id]["suggested_tools"]

    _nlu_context.pop(session_id, None)
