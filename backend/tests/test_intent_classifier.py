"""测试 NLU 引擎的高层意图分类（原 intent_classifier 已合并到 nlu_engine）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.nlu_engine import nlu_engine, IntentCategory


def test_emergency_category():
    result = nlu_engine.parse("我大出血了")
    assert result.category == IntentCategory.EMERGENCY


def test_knowledge_category():
    result = nlu_engine.parse("什么是妊娠期高血压")
    assert result.category == IntentCategory.KNOWLEDGE


def test_chat_default_category():
    result = nlu_engine.parse("你好")
    assert result.category == IntentCategory.CHAT


def test_unknown_intent_with_analyze_keyword():
    result = nlu_engine.parse("帮我分析一下情况")
    assert result.category == IntentCategory.ANALYZE


def test_unknown_intent_with_followup_keyword():
    result = nlu_engine.parse("安排一次随访")
    assert result.category == IntentCategory.FOLLOWUP
